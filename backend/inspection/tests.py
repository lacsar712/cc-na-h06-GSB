import importlib

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from inspection.models import Inspection
from inspection.rules import (
    BEARING_TOLERANCE_DEG,
    FAIL_VERDICT,
    PASS_NOTE,
    PASS_VERDICT,
    judge,
)


class JudgeRuleTests(TestCase):
    def test_pass_when_intensity_meets_requirement_and_bearing_within_tolerance(self):
        verdict, note = judge(1400, 1200, 0.4)
        self.assertEqual((verdict, note), (PASS_VERDICT, PASS_NOTE))

    def test_pass_at_boundary_values(self):
        # equal intensity and exactly-tolerance bearing must still pass
        self.assertEqual(judge(1200, 1200, 0)[0], PASS_VERDICT)
        self.assertEqual(judge(1200, 1200, BEARING_TOLERANCE_DEG)[0], PASS_VERDICT)
        self.assertEqual(judge(1200, 1200, -BEARING_TOLERANCE_DEG)[0], PASS_VERDICT)

    def test_fail_when_intensity_insufficient(self):
        verdict, note = judge(800, 1200, 0.2)
        self.assertEqual(verdict, FAIL_VERDICT)
        self.assertEqual(note, "光强不足")

    def test_fail_when_bearing_deviation_too_large(self):
        verdict, note = judge(1400, 1200, 2.5)
        self.assertEqual(verdict, FAIL_VERDICT)
        self.assertEqual(note, "方位偏差过大")

    def test_fail_on_negative_bearing_beyond_tolerance(self):
        self.assertEqual(judge(1400, 1200, -2.1)[0], FAIL_VERDICT)

    def test_intensity_shortfall_dominates_bearing(self):
        verdict, note = judge(800, 1200, 9)
        self.assertEqual((verdict, note), (FAIL_VERDICT, "光强不足"))


class VerdictPolishAbolishedTests(TestCase):
    def test_verdict_polish_module_is_gone(self):
        # The side-channel must never come back: no module, no name to import.
        with self.assertRaises(ImportError):
            importlib.import_module("inspection.verdict_polish")

    def test_views_source_does_not_reference_polish(self):
        from inspection import views

        self.assertNotIn("polish", views.__file__)  # module path sanity
        source = open(views.__file__, encoding="utf-8").read()
        self.assertNotIn("polish", source)


class CreateViewVerdictTests(TestCase):
    def setUp(self):
        self.group = Group.objects.create(name="inspector")
        self.user = User.objects.create_user(username="keeper", password="light123456")
        self.user.groups.add(self.group)
        self.client.force_login(self.user)
        self.url = reverse("create")

    def _post(self, measured, required, bearing, code="LH-X"):
        return self.client.post(
            self.url,
            {
                "aid_code": code,
                "measured_cd": measured,
                "required_cd": required,
                "bearing_error_deg": bearing,
            },
        )

    def test_fail_verdict_is_stored_verbatim(self):
        response = self._post(800, 1200, 0.2)
        row = Inspection.objects.get(aid_code="LH-X")
        self.assertEqual(row.verdict, FAIL_VERDICT)
        self.assertEqual(row.note, "光强不足")
        self.assertRedirects(response, reverse("detail", args=[row.pk]))

    def test_bearing_fail_verdict_is_stored_verbatim(self):
        self._post(1400, 1200, 3.0, code="LH-B")
        row = Inspection.objects.get(aid_code="LH-B")
        self.assertEqual((row.verdict, row.note), (FAIL_VERDICT, "方位偏差过大"))

    def test_pass_verdict_is_stored_verbatim(self):
        self._post(1400, 1200, 0.4, code="LH-OK")
        row = Inspection.objects.get(aid_code="LH-OK")
        self.assertEqual((row.verdict, row.note), (PASS_VERDICT, PASS_NOTE))


class DetailHeadingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="watch", password="watch123456")
        self.client.force_login(self.user)

    def test_fail_detail_heading_shows_fail(self):
        row = Inspection.objects.create(
            aid_code="LH-09",
            measured_cd=800,
            required_cd=1200,
            bearing_error_deg=0.2,
            verdict=FAIL_VERDICT,
            note="光强不足",
            created_by="keeper",
        )
        content = self.client.get(reverse("detail", args=[row.pk])).content.decode()
        self.assertIn('class="bad">不合格 · 光强不足', content)
        # heading must not be whitewashed into a pass anywhere on the page
        self.assertNotIn('class="ok"', content)
        self.assertNotIn(">合格<", content)
        self.assertNotIn(PASS_NOTE, content)

    def test_pass_detail_heading_shows_pass(self):
        row = Inspection.objects.create(
            aid_code="LH-01",
            measured_cd=1400,
            required_cd=1200,
            bearing_error_deg=0.4,
            verdict=PASS_VERDICT,
            note=PASS_NOTE,
            created_by="keeper",
        )
        content = self.client.get(reverse("detail", args=[row.pk])).content.decode()
        self.assertIn('class="ok">合格 · 光强与方位均在限内', content)
        self.assertNotIn('class="bad"', content)


class ListDotTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="watch", password="watch123456")
        self.client.force_login(self.user)

    def test_fail_row_paints_red_dot_and_fail_label(self):
        Inspection.objects.create(
            aid_code="LH-09", measured_cd=800, required_cd=1200,
            bearing_error_deg=0.2, verdict=FAIL_VERDICT, note="光强不足",
            created_by="keeper",
        )
        content = self.client.get(reverse("list")).content.decode()
        self.assertIn('<td class="bad">不合格</td>', content)
        self.assertNotIn('<td class="ok">合格</td>', content)

    def test_pass_row_paints_green_dot_and_pass_label(self):
        Inspection.objects.create(
            aid_code="LH-01", measured_cd=1400, required_cd=1200,
            bearing_error_deg=0.4, verdict=PASS_VERDICT, note=PASS_NOTE,
            created_by="keeper",
        )
        content = self.client.get(reverse("list")).content.decode()
        self.assertIn('<td class="ok">合格</td>', content)
        self.assertNotIn('<td class="bad">不合格</td>', content)

    def test_verdict_css_property_matches_verdict(self):
        fail = Inspection(verdict=FAIL_VERDICT)
        ok = Inspection(verdict=PASS_VERDICT)
        self.assertEqual(fail.verdict_css, "bad")
        self.assertEqual(ok.verdict_css, "ok")


class SeedDemoTests(TestCase):
    def test_seed_keeps_bright_pass_and_dim_fail_intact(self):
        call_command("seed_demo")
        bright = Inspection.objects.get(aid_code="LH-01")
        dim = Inspection.objects.get(aid_code="LH-09")
        self.assertEqual((bright.verdict, bright.note), (PASS_VERDICT, PASS_NOTE))
        self.assertEqual(bright.verdict_css, "ok")
        self.assertEqual((dim.verdict, dim.note), (FAIL_VERDICT, "光强不足"))
        self.assertEqual(dim.verdict_css, "bad")

        # accounts and permissions
        self.assertTrue(User.objects.get(username="keeper").groups.filter(name="inspector").exists())
        self.assertFalse(User.objects.get(username="watch").groups.filter(name="inspector").exists())
        self.assertTrue(User.objects.get(username="keeper").check_password("light123456"))

    def test_seed_is_idempotent_and_never_relabels_existing_rows(self):
        call_command("seed_demo")
        call_command("seed_demo")
        self.assertEqual(Inspection.objects.count(), 2)
        self.assertEqual(Inspection.objects.get(aid_code="LH-09").verdict, FAIL_VERDICT)
