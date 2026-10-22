import sys,copy,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from rewrite_diverse_corpus import constrained_schema,SCHEMA,validate
class DiversitySchemaTests(unittest.TestCase):
 def test_resource_enums_do_not_leak_into_text_or_numbers(self):
  original=copy.deepcopy(SCHEMA)
  source={"retrieved_context":{"courses":[{"course_id":"COURSE"}],"certifications":[{"cert_id":7}],"books":[{"isbn":"ISBN"}],"regulation_rag":{"approved":[{"rag_chunk_id":"CHUNK"}]}}}
  s=constrained_schema(source)
  self.assertEqual(SCHEMA,original)
  self.assertNotIn("enum",s["properties"]["scenario"]["properties"]["goal"])
  self.assertEqual(s["properties"]["scenario"]["properties"]["constraints"]["properties"]["duration_weeks"]["enum"],list(range(1,17)))
  stage=s["properties"]["answer"]["properties"]["milestones"]["items"]["properties"]
  self.assertEqual(stage["phase_name"],{"type":"string"})
  self.assertEqual(stage["recommended_courses"]["items"]["properties"]["course_id"]["enum"],["COURSE"])
  self.assertEqual(stage["recommended_certifications"]["items"]["properties"]["cert_id"]["enum"],[7])
  other=constrained_schema({"retrieved_context":{}})
  self.assertEqual(other["properties"]["answer"]["properties"]["regulation_citations"]["maxItems"],0)
  self.assertNotIn("enum",other["properties"]["scenario"]["properties"]["goal"])
if __name__=="__main__":unittest.main()
