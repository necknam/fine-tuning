"""Server-side PostgreSQL persistence using SUPABASE_DB_URL; no memory fallback."""
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

from src.database.deployment import CATALOG, LEGACY_ARCHIVE, connect, ident
from pathlib import Path
import json
from src.database.final_schema import RENAMES

CURRENT_CATALOG = json.loads(Path(__file__).with_name("catalog.current.json").read_text(encoding="utf-8"))


class DatabaseOperationError(RuntimeError):
    pass


def user_id_value(value):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError('users.user_id must be an integer, not a profile ID or UUID.')
    if isinstance(value, str) and not value.isdecimal():
        raise ValueError('users.user_id must be an integer, not a profile ID or UUID.')
    result = int(value)
    if result <= 0 or result > 2147483647:
        raise ValueError('users.user_id is outside the positive PostgreSQL INTEGER range.')
    return result


def serializable(value):
    if isinstance(value, dict):
        return {key: serializable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serializable(item) for item in value]
    if isinstance(value, (UUID, date, datetime, Decimal)):
        return str(value)
    return value


class Query:
    """Small compatibility layer for existing .client.table(...) call sites."""
    def __init__(self, db, table):
        self.db = db
        if '.' in table:
            self.full_table = table
            self.table_name = table.split('.')[1]
        elif ('public.' + table) in CATALOG:
            self.full_table = 'public.' + table
            self.table_name = table
        elif ('regulations.' + table) in CURRENT_CATALOG:
            self.full_table = 'regulations.' + table
            self.table_name = table
        elif ('hr_regulation_pilot.' + table) in CATALOG:
            self.full_table = 'hr_regulation_pilot.' + table
            self.table_name = table
        else:
            self.full_table = 'public.' + table
            self.table_name = table
        self.full_table = LEGACY_ARCHIVE.get(self.full_table, self.full_table)
        if self.full_table in {'growpath_legacy.ai_cases','growpath_legacy.regulations','growpath_legacy.user_skill_gap','growpath_legacy.employee_skill_gaps'}:
            raise ValueError('Retired archive table is not available')
        self.full_table = RENAMES.get(self.full_table, self.full_table)
        self.spec = CURRENT_CATALOG.get(self.full_table) or CATALOG.get(self.full_table)
        if self.spec is None:
            raise ValueError('Unsupported public table')
        if self.full_table in {'public.roadmap_generations','public.roadmap_selections','public.roadmap_reports','public.assessment_reports','public.prompt_evaluations','public.prompt_optimizations'}:
            raise ValueError('Use the canonical database persistence methods for this retired table')
        self.columns = {c['column']: c for c in self.spec['columns']}
        self.operation, self.fields = 'select', '*'
        self.filters, self.sorts, self.cap = [], [], None
        self.payload, self.conflict = None, None

    def column(self, field):
        if field not in self.columns:
            raise ValueError(f'Unknown column: {self.table_name}.{field}')
        return ident(field)

    def select(self, fields='*'):
        self.fields = '*' if fields == '*' else ', '.join(self.column(f.strip()) for f in fields.split(','))
        return self

    def _filter(self, field, operator, value):
        self.filters.append((self.column(field), operator, value))
        return self

    def eq(self, field, value): return self._filter(field, '=', value)
    def neq(self, field, value): return self._filter(field, '<>', value)
    def ilike(self, field, value): return self._filter(field, 'ILIKE', value)
    def gte(self, field, value): return self._filter(field, '>=', value)
    def lte(self, field, value): return self._filter(field, '<=', value)
    def in_(self, field, values): return self._filter(field, '= ANY', list(values))

    def order(self, field, desc=False):
        self.sorts.append(self.column(field) + (' DESC' if desc else ' ASC'))
        return self

    def limit(self, value):
        if type(value) is not int or not 1 <= value <= 10000:
            raise ValueError('limit must be 1..10000')
        self.cap = value
        return self

    def insert(self, data):
        self.operation, self.payload = 'insert', data
        return self

    def upsert(self, data, on_conflict=None):
        self.operation, self.payload = 'upsert', data
        self.conflict = on_conflict.split(',') if on_conflict else self.spec['pk']
        return self

    def update(self, data):
        self.operation, self.payload = 'update', data
        return self

    def delete(self):
        self.operation = 'delete'
        return self

    def value(self, field, value):
        self.column(field)
        col_type = self.columns[field]['type'].lower()
        if value is not None and col_type == 'jsonb':
            from psycopg.types.json import Jsonb
            return Jsonb(serializable(value))
        if value is not None and col_type.startswith('vector(') and isinstance(value, list):
            import json
            return json.dumps(value, allow_nan=False)
        if value is not None and isinstance(value, dict):
            from psycopg.types.json import Jsonb
            return Jsonb(serializable(value))
        return value

    def _run(self, conn):
        schema_part, table_part = self.full_table.split('.')
        table = ident(schema_part) + '.' + ident(table_part)
        predicates, params = [], []
        for col, operator, value in self.filters:
            if value is None and operator in ('=', '<>'):
                predicates.append(col + (' IS NULL' if operator == '=' else ' IS NOT NULL'))
            else:
                predicates.append(col + (' = ANY(%s)' if operator == '= ANY' else f' {operator} %s'))
                params.append(value)
        where = ' WHERE ' + ' AND '.join(predicates) if predicates else ''
        if self.operation == 'select':
            statement = f'SELECT {self.fields} FROM {table}' + where
            if self.sorts:
                statement += ' ORDER BY ' + ', '.join(self.sorts)
            if self.cap is not None:
                statement += ' LIMIT %s'
                params.append(self.cap)
            return conn.execute(statement, params).fetchall()
        if self.operation in ('delete', 'update'):
            if not where:
                raise ValueError('UPDATE and DELETE require explicit filters')
            if self.operation == 'delete':
                return conn.execute(f'DELETE FROM {table}' + where + ' RETURNING *', params).fetchall()
            fields = list(self.payload)
            if not fields:
                raise ValueError('Empty update')
            assignments = ', '.join(self.column(f) + '=%s' for f in fields)
            values = [self.value(f, self.payload[f]) for f in fields]
            return conn.execute(f'UPDATE {table} SET {assignments}' + where + ' RETURNING *', values + params).fetchall()
        rows = self.payload if isinstance(self.payload, list) else [self.payload]
        returned = []
        for row in rows:
            fields = list(row)
            if not fields:
                raise ValueError('Empty insert')
            statement = f'INSERT INTO {table} ({", ".join(self.column(f) for f in fields)}) VALUES ({", ".join(["%s"] * len(fields))})'
            if self.operation == 'upsert':
                keys = [key.strip() for key in self.conflict]
                statement += ' ON CONFLICT (' + ', '.join(self.column(k) for k in keys) + ') '
                updates = [f for f in fields if f not in keys]
                statement += ('DO UPDATE SET ' + ', '.join(self.column(f) + '=EXCLUDED.' + self.column(f) for f in updates)) if updates else 'DO NOTHING'
            returned.extend(conn.execute(statement + ' RETURNING *', [self.value(f, row[f]) for f in fields]).fetchall())
        return returned

    def execute(self):
        with self.db.transaction() as conn:
            rows = serializable(self._run(conn))
        return SimpleNamespace(data=rows, count=len(rows))


class DatabaseClient:
    def __init__(self, connection=None):
        self._connection = connection  # Optional caller-owned connection for transaction tests.
        self.client = self

    @contextmanager
    def transaction(self):
        try:
            if self._connection is not None:
                with self._connection.transaction():
                    yield self._connection
            else:
                with connect('SUPABASE_DB_URL') as conn:
                    yield conn
        except (ValueError, DatabaseOperationError):
            raise
        except Exception as exc:
            raise DatabaseOperationError(f'DB operation failed ({type(exc).__name__}); transaction rolled back. Check DB connection and schema.') from None

    def table(self, name): return Query(self, name)

    def _rows(self, table, filters=None, order=None):
        query = self.table(table).select()
        for field, value in (filters or {}).items():
            query.eq(field, value)
        if order:
            query.order(order)
        return query.execute().data

    def _one(self, table, filters):
        rows = self._rows(table, filters)
        return rows[0] if rows else None

    def _session_lock(self, conn, session_id):
        row = conn.execute('SELECT session_id, current_stage FROM public.roadmap_sessions WHERE session_id=%s FOR UPDATE', (session_id,)).fetchone()
        if row is None:
            raise ValueError('Project session does not exist.')
        return row

    def check_health(self):
        try:
            with self.transaction() as conn:
                conn.execute('SET TRANSACTION READ ONLY')
                conn.execute('SELECT user_id,name FROM public.users LIMIT 1').fetchall()
            return {'connected': True, 'message': 'PostgreSQL connected', 'storage': 'postgresql'}
        except (RuntimeError, ValueError):
            return {'connected': False, 'message': 'SUPABASE_DB_URL connection/schema check failed', 'storage': 'postgresql'}

    def list_skill_tags(self):
        return self.table('skill_tags').select('skill_id,name,category').order('skill_id').execute().data

    def fetch_mock_profiles(self):
        return self._rows('test_mock_profiles')


    def create_roadmap_session(self, user_id=None, project_name=None, status='DRAFT', current_stage=1, **kwargs):
        uid = user_id_value(user_id)
        if not project_name or not str(project_name).strip():
            raise ValueError('Project name is required.')
        row = self.table('roadmap_sessions').insert({'user_id': uid, 'project_name': str(project_name).strip()[:255],
            'status': status, 'current_stage': current_stage}).execute().data[0]
        return row['session_id']

    def get_roadmap_session(self, session_id): return self._one('roadmap_sessions', {'session_id': session_id})

    def list_roadmap_sessions(self, user_id=None, limit=10):
        query = self.table('roadmap_sessions').select().order('created_at', desc=True).limit(limit)
        if user_id is not None:
            query.eq('user_id', user_id_value(user_id))
        return query.execute().data

    def update_session_stage(self, session_id, stage_num, status='IN_PROGRESS'):
        if type(stage_num) is not int or not 1 <= stage_num <= 7:
            raise ValueError('stage_num must be 1..7')
        rows = self.table('roadmap_sessions').update({'current_stage': stage_num, 'status': status,
            'updated_at': datetime.now(timezone.utc)}).eq('session_id', session_id).execute().data
        if not rows:
            raise ValueError('Project session does not exist.')
        return True


    def get_project_plan(self, session_id): return self._one('project_plans', {'session_id': session_id})



    @staticmethod
    def _assessment_type(value):
        if value not in ('PRE', 'POST'):
            raise ValueError('assessment_type must be PRE or POST')
        return value














    def get_active_prompts(self):
        rows = self._rows('prompt_versions', {'is_active': True})
        if len({r['agent_id'] for r in rows}) != len(rows):
            raise ValueError('Multiple active prompt versions for an agent.')
        return {r['agent_id']: r for r in rows}

    def get_active_prompt_for_agent(self, agent_id): return self.get_active_prompts().get(agent_id)

    def get_prompt_history(self, agent_id):
        return self.table('prompt_versions').select().eq('agent_id', agent_id).order('version_num', desc=True).execute().data

    def create_prompt_version(self, **kwargs): return self.table('prompt_versions').insert(kwargs).execute().data[0]

    def activate_prompt_version(self, prompt_version_id, agent_id):
        with self.transaction() as conn:
            conn.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', ('prompt:' + agent_id,))
            target = conn.execute('SELECT 1 FROM public.prompt_versions WHERE prompt_version_id=%s AND agent_id=%s',
                                   (prompt_version_id, agent_id)).fetchone()
            if not target:
                raise ValueError('Prompt version does not belong to this agent.')
            self.table('prompt_versions').update({'is_active': False, 'deactivated_at': datetime.now(timezone.utc)}).eq('agent_id', agent_id)._run(conn)
            self.table('prompt_versions').update({'is_active': True, 'deactivated_at': None}).eq('prompt_version_id', prompt_version_id)._run(conn)
        return True

    def rollback_prompt_version(self, agent_id):
        current = self.get_active_prompt_for_agent(agent_id)
        if not current or not current.get('parent_version_id'):
            return {'success': False, 'message': 'No parent version'}
        parent = current['parent_version_id']
        return {'success': self.activate_prompt_version(parent, agent_id), 'restored_parent_id': parent}





    def get_evaluation_schemas(self, evaluation_kind=None):
        query = self.table('evaluation_result_schema').select()
        if evaluation_kind:
            query.eq('evaluation_kind', evaluation_kind)
        return query.execute().data

    def get_evaluation_items(self, schema_id):
        return self.table('evaluation_item_definition').select().eq('evaluation_result_schema_id', schema_id).order('display_order').execute().data

    def get_evaluation_sources(self, schema_id, item_id=None):
        query = self.table('evaluation_schema_source').select().eq('evaluation_result_schema_id', schema_id)
        if item_id:
            query.eq('evaluation_item_definition_id', item_id)
        return query.execute().data


from .app_store import extend
DatabaseClient = extend(DatabaseClient)
db_client = DatabaseClient()
__all__ = ['DatabaseClient', 'DatabaseOperationError', 'db_client', 'user_id_value']