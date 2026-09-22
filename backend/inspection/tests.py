import importlib
from pathlib import Path

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import Client, TestCase

from inspection.models import Inspection
from inspection.rules import judge

PASS = "合格"
PASS_NOTE = "光强与方位均在限内"
FAIL = "不合格"


class JudgeTests(TestCase):
    """判定函数：合格 / 不合格两个方向都要覆盖。"""

    def test_pass_when_intensity_and_bearing_within_limits(self):
        self.assertEqual(judge(1400, 1200, 0.4), (PASS, PASS_NOTE))

    def test_pass_on_boundary(self):
        # 光强刚好达标、偏差刚好在 2 度限内
        self.assertEqual(judge(1200, 1200, 2.0), (PASS, PASS_NOTE))
        self.assertEqual(judge(1200, 1200, -2.0), (PASS, PASS_NOTE))

    def test_fail_when_intensity_insufficient(self):
        self.assertEqual(judge(800, 1200, 0.2), (FAIL, "光强不足"))

    def test_fail_when_bearing_off(self):
        self.assertEqual(judge(1200, 1200, 2.5), (FAIL, "方位偏差过大"))
        self.assertEqual(judge(1200, 1200, -2.5), (FAIL, "方位偏差过大"))

    def test_fail_takes_precedence_when_both_bad(self):
        self.assertEqual(judge(800, 1200, 9.0), (FAIL, "光强不足"))


class VerdictPersistenceTests(TestCase):
    """落库判词：judge 给什么，库里就必须是什么，禁止任何旁路改写。"""

    def setUp(self):
        self.client = Client()
        self.group = Group.objects.create(name="inspector")
        self.user = User.objects.create_user(username="keeper", password="x")
        self.user.groups.add(self.group)
        self.client.force_login(self.user)

    def _post(self, code, measured, required=1200, bearing=0.0):
        return self.client.post(
            "/inspections/new/",
            {
                "aid_code": code,
                "measured_cd": str(measured),
                "required_cd": str(required),
                "bearing_error_deg": str(bearing),
            },
        )

    def test_failing_inspection_is_stored_as_fail(self):
        # 回归：VerdictPolish 曾在保存时把“不合格”粉饰为“合格”
        resp = self._post("LH-09", 800)
        self.assertEqual(resp.status_code, 302)
        row = Inspection.objects.get(aid_code="LH-09")
        self.assertEqual(row.verdict, FAIL)
        self.assertEqual(row.note, "光强不足")
        self.assertEqual(row.created_by, "keeper")

    def test_passing_inspection_is_stored_as_pass(self):
        resp = self._post("LH-01", 1400, bearing=0.4)
        self.assertEqual(resp.status_code, 302)
        row = Inspection.objects.get(aid_code="LH-01")
        self.assertEqual(row.verdict, PASS)
        self.assertEqual(row.note, PASS_NOTE)

    def test_bearing_fail_is_stored_as_fail(self):
        resp = self._post("LH-07", 1400, bearing=3.0)
        self.assertEqual(resp.status_code, 302)
        row = Inspection.objects.get(aid_code="LH-07")
        self.assertEqual(row.verdict, FAIL)
        self.assertEqual(row.note, "方位偏差过大")

    def test_non_inspector_cannot_create(self):
        outsider = User.objects.create_user(username="watch", password="x")
        self.client.force_login(outsider)
        resp = self._post("LH-99", 800)
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(Inspection.objects.filter(aid_code="LH-99").exists())


class VerdictDisplayTests(TestCase):
    """总表色点 + 详情抬头：两处都必须忠于真实结论。"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="watch", password="x")
        self.client.force_login(self.user)
        self.bad = Inspection.objects.create(
            aid_code="LH-09",
            measured_cd=800,
            required_cd=1200,
            bearing_error_deg=0.2,
            verdict=FAIL,
            note="光强不足",
            created_by="keeper",
        )
        self.good = Inspection.objects.create(
            aid_code="LH-01",
            measured_cd=1400,
            required_cd=1200,
            bearing_error_deg=0.4,
            verdict=PASS,
            note=PASS_NOTE,
            created_by="keeper",
        )

    def test_list_paints_red_dot_for_fail_and_green_for_pass(self):
        body = self.client.get("/").content.decode()
        self.assertIn('<td class="bad">不合格</td>', body)
        self.assertIn('<td class="ok">合格</td>', body)
        # 不合格行的说明也必须原样展示，不得替换
        self.assertIn("光强不足", body)

    def test_detail_heading_keeps_fail(self):
        body = self.client.get(f"/inspections/{self.bad.pk}/").content.decode()
        self.assertIn('<p class="bad">不合格 · 光强不足</p>', body)
        self.assertNotIn('class="ok"', body)
        self.assertNotIn(PASS_NOTE, body)

    def test_detail_heading_keeps_pass(self):
        body = self.client.get(f"/inspections/{self.good.pk}/").content.decode()
        self.assertIn(f'<p class="ok">{PASS} · {PASS_NOTE}</p>', body)
        self.assertNotIn('class="bad"', body)


class SeedDemoTests(TestCase):
    """明亮种子：一合格一不合格，均不得被改坏；重复执行不重复造数。"""

    def test_seed_keeps_one_pass_and_one_fail(self):
        call_command("seed_demo")
        good = Inspection.objects.get(aid_code="LH-01")
        bad = Inspection.objects.get(aid_code="LH-09")
        self.assertEqual((good.verdict, good.note), (PASS, PASS_NOTE))
        self.assertEqual((bad.verdict, bad.note), (FAIL, "光强不足"))
        self.assertEqual(Inspection.objects.count(), 2)

        call_command("seed_demo")
        self.assertEqual(Inspection.objects.count(), 2)


class VerdictPolishRemovedTests(TestCase):
    """名为 VerdictPolish 的旁路必须彻底废除，不留模块、不留调用、不留模板痕迹。"""

    def test_polish_module_is_gone(self):
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("inspection.verdict_polish")

    def test_views_no_longer_reference_polish(self):
        import inspection.views as views

        self.assertFalse(hasattr(views, "polish_write"))
        self.assertFalse(hasattr(views, "polish_detail_heading"))
        source = Path(views.__file__).read_text(encoding="utf-8").lower()
        self.assertNotIn("polish", source)

    def test_templates_no_longer_reference_polish(self):
        templates_dir = Path(__file__).resolve().parent.parent / "templates"
        for name in ("list.html", "detail.html"):
            text = (templates_dir / name).read_text(encoding="utf-8").lower()
            self.assertNotIn("polish", text)
            self.assertNotIn("verdictpolish", text)
