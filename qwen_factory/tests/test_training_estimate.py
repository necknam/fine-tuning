import ast
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
LOG=""" 11%|x| 51/470 [05:15<43:13, 6.19s/it]
 11%|x| 51/470 [05:15<43:13, 6.19s/it]
 11%|x| 52/470 [05:36<45:56, 6.59s/it]
 11%|x| 53/470 [06:00<50:10, 7.22s/it]"""


def source(name):
    text=(ROOT/'scripts/local_dashboard.py').read_text(encoding='utf-8')
    node=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name==name)
    return ast.get_source_segment(text,node)


class ResumedEstimateTests(unittest.TestCase):
    def speed(self,text):
        namespace={};exec(source('measured_training_speed'),namespace)
        return namespace['measured_training_speed'](text,470)

    def test_resumed_progress_uses_actual_new_step_intervals(self):
        self.assertEqual(self.speed(LOG),22.5)

    def test_first_resumed_step_has_no_measured_interval(self):
        self.assertIsNone(self.speed(LOG.splitlines()[0]))

    def test_loading_progress_and_duplicate_lines_do_not_distort_speed(self):
        text='Loading weights: 1%|x| 1/470 [00:01<00:01, 1s/it]\n'+LOG
        self.assertEqual(self.speed(text),22.5)

    def test_ui_estimates_remaining_steps_not_the_full_training_run(self):
        import yaml
        from streamlit.testing.v1 import AppTest
        cfg=yaml.safe_load((ROOT/'configs/hyperparameters.compare.reviewed_v4_full1500.yaml').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'recipe.yaml').write_text(yaml.safe_dump(cfg),encoding='utf-8')
            code=('import streamlit as st\nimport yaml\nfrom pathlib import Path\nROOT=Path('+repr(d)+')\n'
                  +'def duration_text(seconds): return str(int(seconds))\n'
                  +source('measured_training_speed')+'\n'+source('show_measured_estimate')+'\n'
                  +'show_measured_estimate('+repr({'config':'recipe.yaml','job_id':'resume','log_tail':LOG})+',None,None)\n')
            app=AppTest.from_string(code,default_timeout=15).run()
            self.assertEqual(len(app.exception),0)
            self.assertEqual(app.metric[0].value,'9382')
            self.assertTrue(any('53/470' in item.value for item in app.caption))

if __name__=='__main__':unittest.main()
