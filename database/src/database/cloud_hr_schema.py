"""Clone operational HR definitions to a private Cloud schema, without copying rows."""
import hashlib,json,re
from psycopg import sql

TABLES=('employees','employee_skills','employee_certifications','employee_education_records','employee_recommended_prompts')
TARGET='growpath_hr'

def rewrite_definition(text):
    for name in TABLES:
        text=re.sub(r'\bpublic\.'+name+r'\b',TARGET+'.'+name,text)
    # Other public references are shared catalog master tables.
    return text.replace('public.','growpath_live.')

def synchronize_schema(source,target):
    """Caller owns target transaction; this function never copies employee rows."""
    target.execute('SELECT pg_advisory_xact_lock(763250133)')
    source_specs={}
    for name in TABLES:
        source_specs[name]=source.execute("""SELECT a.attname AS column,format_type(a.atttypid,a.atttypmod) AS type,
          a.attnotnull AS not_null,pg_get_expr(d.adbin,d.adrelid) AS default,a.attidentity AS identity
          FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
          WHERE a.attrelid=%s::regclass AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum""",('public.'+name,)).fetchall()
    existing=target.execute("SELECT tablename FROM pg_tables WHERE schemaname=%s",(TARGET,)).fetchall()
    if existing:
        if {r['tablename'] for r in existing}!=set(TABLES):raise ValueError('Existing Cloud HR schema differs; refusing overwrite')
        created=False
    else:
        target.execute(sql.SQL('CREATE SCHEMA IF NOT EXISTS {}; REVOKE ALL ON SCHEMA {} FROM PUBLIC').format(sql.Identifier(TARGET),sql.Identifier(TARGET)))
        target.execute(sql.SQL('SET LOCAL search_path TO {},growpath_live,extensions,public').format(sql.Identifier(TARGET)))
        for name,cols in source_specs.items():
            definitions=[]
            for col in cols:
                definition=sql.SQL('{} {}').format(sql.Identifier(col['column']),sql.SQL(col['type']))
                if col['identity']:
                    definition+=sql.SQL(' GENERATED '+('ALWAYS' if col['identity']=='a' else 'BY DEFAULT')+' AS IDENTITY')
                elif col['default']:
                    default=col['default']
                    if default.startswith('nextval('):
                        sequence=name+'_'+col['column']+'_seq'
                        target.execute(sql.SQL('CREATE SEQUENCE {}.{}').format(sql.Identifier(TARGET),sql.Identifier(sequence)))
                        default="nextval('"+TARGET+'.'+sequence+"'::regclass)"
                    definition+=sql.SQL(' DEFAULT '+default)
                if col['not_null']:definition+=sql.SQL(' NOT NULL')
                definitions.append(definition)
            target.execute(sql.SQL('CREATE TABLE {}.{} ({})').format(sql.Identifier(TARGET),sql.Identifier(name),sql.SQL(',').join(definitions)))
        # All tables exist before FK creation. Unqualified master refs resolve via search_path.
        for name in TABLES:
            constraints=source.execute('SELECT conname,pg_get_constraintdef(oid) AS definition FROM pg_constraint WHERE conrelid=%s::regclass ORDER BY CASE contype WHEN \'p\' THEN 0 WHEN \'u\' THEN 1 WHEN \'f\' THEN 3 ELSE 2 END,conname',('public.'+name,)).fetchall()
            for item in constraints:
                target.execute(sql.SQL('ALTER TABLE {}.{} ADD CONSTRAINT {} {}').format(sql.Identifier(TARGET),sql.Identifier(name),sql.Identifier(item['conname']),sql.SQL(rewrite_definition(item['definition']))))
            indexes=source.execute("""SELECT pg_get_indexdef(i.indexrelid) AS definition FROM pg_index i
              WHERE i.indrelid=%s::regclass AND NOT EXISTS(SELECT 1 FROM pg_constraint c WHERE c.conindid=i.indexrelid)""",('public.'+name,)).fetchall()
            for item in indexes:target.execute(rewrite_definition(item['definition']))
            target.execute(sql.SQL('ALTER TABLE {}.{} ENABLE ROW LEVEL SECURITY').format(sql.Identifier(TARGET),sql.Identifier(name)))
            target.execute(sql.SQL('REVOKE ALL ON TABLE {}.{} FROM PUBLIC').format(sql.Identifier(TARGET),sql.Identifier(name)))
        created=True
    checked={}
    for name,cols in source_specs.items():
        actual=target.execute("""SELECT a.attname AS column,format_type(a.atttypid,a.atttypmod) AS type,a.attnotnull AS not_null
          FROM pg_attribute a WHERE a.attrelid=%s::regclass AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum""",(TARGET+'.'+name,)).fetchall()
        if actual!=[{k:r[k] for k in ('column','type','not_null')} for r in cols]:raise ValueError('Cloud column mismatch: '+name)
        count=target.execute(sql.SQL('SELECT count(*) AS n FROM {}.{}').format(sql.Identifier(TARGET),sql.Identifier(name))).fetchone()['n']
        if count and target.execute("SELECT count(*) AS n FROM growpath_hr.employees WHERE source_type<>'TEST_MANUAL'").fetchone()['n']:
            raise ValueError('Unexpected non-test employee data; refusing automatic schema action')
        if not target.execute('SELECT relrowsecurity FROM pg_class WHERE oid=%s::regclass',(TARGET+'.'+name,)).fetchone()['relrowsecurity']:raise ValueError('RLS missing')
        def foreign_keys(connection,qualified):
            return connection.execute("""SELECT co.conname,n.nspname AS target_schema,t.relname AS target_table,
              ARRAY(SELECT a.attname FROM unnest(co.conkey) WITH ORDINALITY k(num,ord) JOIN pg_attribute a ON a.attrelid=co.conrelid AND a.attnum=k.num ORDER BY ord) AS columns,
              ARRAY(SELECT a.attname FROM unnest(co.confkey) WITH ORDINALITY k(num,ord) JOIN pg_attribute a ON a.attrelid=co.confrelid AND a.attnum=k.num ORDER BY ord) AS target_columns
              FROM pg_constraint co JOIN pg_class t ON t.oid=co.confrelid JOIN pg_namespace n ON n.oid=t.relnamespace
              WHERE co.conrelid=%s::regclass AND co.contype='f' ORDER BY co.conname""",(qualified,)).fetchall()
        expected=foreign_keys(source,'public.'+name)
        for item in expected:item['target_schema']=TARGET if item['target_table'] in TABLES else 'growpath_live'
        if expected!=foreign_keys(target,TARGET+'.'+name):raise ValueError('Cloud FK mismatch: '+name)
        checked[name]={'columns':len(cols),'rows':count}
    return {'schema':TARGET,'created':created,'tables':checked,'employee_rows_copied':0,
            'schema_sha256':hashlib.sha256(json.dumps(source_specs,sort_keys=True,default=str).encode()).hexdigest()}
