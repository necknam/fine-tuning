from datetime import datetime,timedelta,timezone
from unittest import TestCase
from src.shared.course_enrollment import enrollment_fields,enrollment_status,enrollment_reason

class EnrollmentTests(TestCase):
    def setUp(self):self.now=datetime(2026,10,22,3,tzinfo=timezone.utc)
    def raw(self):return {'public_yn':'Y','enrollment_start':(self.now-timedelta(days=1)).isoformat(),'enrollment_end':(self.now+timedelta(days=1)).isoformat()}
    def test_kmooc_period_preserved(self):
        raw=self.raw();f=enrollment_fields('API_KMOOC',raw)
        self.assertEqual(f['enrollment_start'],raw['enrollment_start']);self.assertEqual(f['enrollment_period_type'],'scheduled')
        self.assertEqual(enrollment_status(f,now=self.now),'ongoing')
    def test_three_statuses_and_end_boundary(self):
        f=enrollment_fields('API_KMOOC',self.raw())
        self.assertEqual(enrollment_status(f,now=self.now-timedelta(days=2)),'upcoming')
        self.assertEqual(enrollment_status(f,now=self.now+timedelta(days=1)),'ongoing')
        self.assertEqual(enrollment_status(f,now=self.now+timedelta(days=2)),'ended')
    def test_ms_missing_period_unrestricted(self):
        f=enrollment_fields('API_MS_LEARN',{})
        self.assertEqual(f,{'enrollment_start':None,'enrollment_end':None,'enrollment_period_type':'unrestricted'})
        self.assertEqual(enrollment_status(f,now=self.now),'ongoing')
    def test_unknown_is_not_unrestricted(self):
        for source,raw in [('API_KMOOC',{}),('API_MS_LEARN',{'enrollment_start':'bad'})]:
            f=enrollment_fields(source,raw)
            self.assertEqual(f['enrollment_period_type'],'unknown');self.assertIsNone(enrollment_status(f,now=self.now))
    def test_bad_order_unknown(self):
        raw=self.raw();raw['enrollment_start'],raw['enrollment_end']=raw['enrollment_end'],raw['enrollment_start']
        f=enrollment_fields('API_KMOOC',raw)
        self.assertEqual(f['enrollment_period_type'],'unknown')
    def test_study_period_not_used(self):
        raw={**self.raw(),'study_start':'2000-01-01','study_end':'2000-02-01'}
        self.assertIsNone(enrollment_reason('API_KMOOC',raw,now=self.now))
    def test_future_closed_and_nonpublic_not_recommended(self):
        raw=self.raw()
        for now in (self.now-timedelta(days=2),self.now+timedelta(days=2)):
            self.assertIsNotNone(enrollment_reason('API_KMOOC',raw,now=now))
        self.assertIsNotNone(enrollment_reason('API_KMOOC',{**raw,'public_yn':'N'},now=self.now))
    def test_stored_period_mismatch_blocked(self):
        raw=self.raw();fields=enrollment_fields('API_KMOOC',raw);fields['enrollment_end']=(self.now+timedelta(days=2)).isoformat()
        self.assertEqual(enrollment_reason('API_KMOOC',raw,fields=fields,now=self.now),'enrollment_period_mismatch')
    def test_unix_seconds_and_milliseconds(self):
        raw={'enrollment_start':str(int(self.now.timestamp())),'enrollment_end':str(int((self.now+timedelta(days=1)).timestamp())*1000)}
        f=enrollment_fields('API_KMOOC',raw)
        self.assertEqual(f['enrollment_start'],self.now.isoformat());self.assertEqual(f['enrollment_period_type'],'scheduled')
    def test_ms_supplied_period_observed(self):
        self.assertEqual(enrollment_fields('API_MS_LEARN',self.raw())['enrollment_period_type'],'scheduled')
