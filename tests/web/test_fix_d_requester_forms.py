"""FIX-D: step-2 intake follow-up fixes to the requester wizard (R1-R9).

Covers, from the FIX-D checklist:
  1. Secondary links (Start over/Resend/Change it/Didn't get it) render before the sticky
     action bar, not after it (visual M2 remainder).
  2. Per-field `aria-invalid`/`aria-describedby` + error-summary anchors that actually match a
     real element id, on R2-R5 (usability M9 remainder).
  3. The >=1280 wizard "Good to know" aside (visual M9 remainder).
  4. R3 "Owner's full name" only required for a family member (visual Minor 4 / usability M9).
  5. R5 "I don't use email" locks the contact-preference group to Phone call, server-enforced
     (visual Minor 5 / usability M9).
  8. R6's step header says "Step 5 of 5", not "Last step" (visual Minor 6).
"""

from __future__ import annotations

import pytest
from django.test import Client
from django.urls import reverse

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _real_portal_lookups(real_portal_lookups):
    pass


def _backdate_form_opened_at(client: Client) -> None:
    import datetime as dt

    from ham.platform.clock import now as clock_now
    from ham.requester_portal import antiabuse
    from ham.rules import RULES
    from ham.web.views_requester import _SESSION_FORM_OPENED_AT

    opened_at = clock_now() - RULES.intake.INTAKE_MIN_FILL_TIME - dt.timedelta(seconds=1)
    session = client.session
    session[_SESSION_FORM_OPENED_AT] = antiabuse.sign_form_opened_at(now=opened_at)
    session.save()


def _begin(client: Client) -> None:
    client.get(reverse("web:request_help_start"))
    resp = client.post(reverse("web:request_help_begin"), follow=True)
    assert resp.status_code == 200
    _backdate_form_opened_at(client)


class TestActionBarPlacement:
    def test_r1_secondary_links_render_before_the_bar(self, client: Client):
        resp = client.get(reverse("web:request_help_start"))
        html = resp.content.decode()
        links_pos = html.index("Already asked? Check on your request")
        bar_pos = html.index('class="form-actions"')
        assert links_pos < bar_pos

    def test_r2_start_over_lives_inside_the_action_bar(self, client: Client):
        _begin(client)
        resp = client.get(reverse("web:request_help_step", kwargs={"step": "need"}))
        html = resp.content.decode()
        bar_start = html.index('class="action-bar"')
        form_end = html.index("</form>", bar_start)
        assert "Start over" in html[bar_start:form_end]
        assert 'form="start-over-form"' in html[bar_start:form_end]

    def test_r8_resend_and_didnt_get_it_render_before_the_bar(self, client: Client):
        _begin(client)
        client.post(
            reverse("web:request_help_step", kwargs={"step": "need"}),
            {"need_category": "roof_or_ceiling", "description": "Water leaks in."},
        )
        client.post(
            reverse("web:request_help_step", kwargs={"step": "home"}),
            {
                "relationship_to_property": "owner",
                "line1": "1400 NW Example Ave",
                "city": "Miami",
                "state": "FL",
                "postal_code": "33125",
                "property_type": "house",
            },
        )
        client.post(
            reverse("web:request_help_step", kwargs={"step": "safety"}), {"hazards": ["none_known"]}
        )
        client.post(
            reverse("web:request_help_step", kwargs={"step": "reaching-you"}),
            {
                "full_name": "Doris Palmer",
                "phone": "(305) 555-0142",
                "email": "doris.p@example.org",
                "contact_preference": "email",
                "availability": ["any_time"],
            },
        )
        client.post(
            reverse("web:request_help_step", kwargs={"step": "review"}),
            {"attested_statements": ["owner_authority", "responsibility"]},
        )
        resp = client.get(reverse("web:request_help_verify"))
        html = resp.content.decode()
        resend_pos = html.index("Resend code")
        bar_pos = html.index('class="action-bar"')
        assert resend_pos < bar_pos
        assert "Didn" in html
        didnt_pos = html.index("Didn", resend_pos)
        assert didnt_pos < bar_pos


class TestFieldAccessibility:
    def test_r2_category_fieldset_has_id_and_error_summary_links_to_it(self, client: Client):
        _begin(client)
        resp = client.post(
            reverse("web:request_help_step", kwargs={"step": "need"}), {"description": ""}
        )
        assert resp.status_code == 422
        html = resp.content.decode()
        assert 'id="id_need_category"' in html
        assert 'href="#id_need_category"' in html
        assert 'aria-invalid="true"' in html
        assert 'aria-describedby="id_need_category-error"' in html
        assert 'id="id_need_category-error"' in html

    def test_r3_relationship_and_property_type_fieldsets_get_error_wiring(self, client: Client):
        _begin(client)
        client.post(
            reverse("web:request_help_step", kwargs={"step": "need"}),
            {"need_category": "roof_or_ceiling", "description": "Water leaks in."},
        )
        resp = client.post(reverse("web:request_help_step", kwargs={"step": "home"}), {})
        assert resp.status_code == 422
        html = resp.content.decode()
        assert 'id="id_relationship_to_property"' in html
        assert 'href="#id_relationship_to_property"' in html
        assert 'id="id_property_type"' in html
        assert 'href="#id_property_type"' in html
        assert 'id="id_line1-error"' in html
        assert 'aria-describedby="id_line1-error"' in html

    def test_r5_contact_preference_and_availability_fieldsets_get_ids(self, client: Client):
        _begin(client)
        client.post(
            reverse("web:request_help_step", kwargs={"step": "need"}),
            {"need_category": "roof_or_ceiling", "description": "Water leaks in."},
        )
        client.post(
            reverse("web:request_help_step", kwargs={"step": "home"}),
            {
                "relationship_to_property": "owner",
                "line1": "1400 NW Example Ave",
                "city": "Miami",
                "state": "FL",
                "postal_code": "33125",
                "property_type": "house",
            },
        )
        client.post(
            reverse("web:request_help_step", kwargs={"step": "safety"}), {"hazards": ["none_known"]}
        )
        resp = client.post(
            reverse("web:request_help_step", kwargs={"step": "reaching-you"}),
            {
                "full_name": "Doris Palmer",
                "phone": "(305) 555-0142",
                "availability": ["not-a-real-choice"],
            },
        )
        assert resp.status_code == 422
        html = resp.content.decode()
        assert 'id="id_contact_preference"' in html
        assert 'href="#id_contact_preference"' in html
        assert 'id="id_availability"' in html
        assert 'href="#id_availability"' in html


class TestWizardAside:
    def test_r1_aside_present(self, client: Client):
        resp = client.get(reverse("web:request_help_start"))
        html = resp.content.decode()
        assert 'class="wizard-aside"' in html
        assert 'aria-label="Good to know"' in html

    def test_r2_r3_r4_r5_r9_have_the_aside(self, client: Client):
        # FIX-H M2: R3 (home) carries a second modifier class,
        # `wizard-aside--repeats-intro`, since its aside repeats the page's own intro line and
        # is hidden below 1280 (still present in the DOM -- still available at >=1280 in its
        # own side column, so this stays a substring check rather than an exact class match).
        _begin(client)
        for step in ["need", "home", "safety", "reaching-you"]:
            resp = client.get(reverse("web:request_help_step", kwargs={"step": step}))
            assert 'class="wizard-aside' in resp.content.decode(), step

    def test_r6_has_no_aside_but_is_wide(self, client: Client):
        _begin(client)
        client.post(
            reverse("web:request_help_step", kwargs={"step": "need"}),
            {"need_category": "roof_or_ceiling", "description": "Water leaks in."},
        )
        client.post(
            reverse("web:request_help_step", kwargs={"step": "home"}),
            {
                "relationship_to_property": "owner",
                "line1": "1400 NW Example Ave",
                "city": "Miami",
                "state": "FL",
                "postal_code": "33125",
                "property_type": "house",
            },
        )
        client.post(
            reverse("web:request_help_step", kwargs={"step": "safety"}), {"hazards": ["none_known"]}
        )
        client.post(
            reverse("web:request_help_step", kwargs={"step": "reaching-you"}),
            {
                "full_name": "Doris Palmer",
                "phone": "(305) 555-0142",
                "email": "doris.p@example.org",
                "contact_preference": "email",
                "availability": ["any_time"],
            },
        )
        resp = client.get(reverse("web:request_help_step", kwargs={"step": "review"}))
        html = resp.content.decode()
        assert "wizard-aside" not in html
        assert "public-card--review" in html
        assert "summary-card-grid" in html


class TestR3OwnerName:
    def test_owner_name_field_not_required_for_tenant(self, client: Client):
        _begin(client)
        client.post(
            reverse("web:request_help_step", kwargs={"step": "need"}),
            {"need_category": "roof_or_ceiling", "description": "Water leaks in."},
        )
        resp = client.post(
            reverse("web:request_help_step", kwargs={"step": "home"}),
            {
                "relationship_to_property": "tenant",
                "line1": "1400 NW Example Ave",
                "city": "Miami",
                "state": "FL",
                "postal_code": "33125",
                "property_type": "house",
            },
            follow=True,
        )
        assert resp.status_code == 200, resp.content

    def test_owner_name_required_for_family_member(self, client: Client):
        _begin(client)
        client.post(
            reverse("web:request_help_step", kwargs={"step": "need"}),
            {"need_category": "roof_or_ceiling", "description": "Water leaks in."},
        )
        resp = client.post(
            reverse("web:request_help_step", kwargs={"step": "home"}),
            {
                "relationship_to_property": "authorized_family_member",
                "line1": "1400 NW Example Ave",
                "city": "Miami",
                "state": "FL",
                "postal_code": "33125",
                "property_type": "house",
            },
        )
        assert resp.status_code == 422
        html = resp.content.decode()
        assert "owner_name" in resp.context["errors"]
        # The field is present (works without JS) and not `hidden` for this relationship.
        assert 'id="owner-name-field"' in html
        field_start = html.index('id="owner-name-field"')
        field_tag_end = html.index(">", field_start)
        assert "hidden" not in html[max(0, field_start - 200) : field_tag_end]


class TestR5NoEmailLocksContactPreference:
    def test_locked_card_shown_and_fieldset_hidden(self, client: Client):
        _begin(client)
        client.post(
            reverse("web:request_help_step", kwargs={"step": "need"}),
            {"need_category": "roof_or_ceiling", "description": "Water leaks in."},
        )
        client.post(
            reverse("web:request_help_step", kwargs={"step": "home"}),
            {
                "relationship_to_property": "owner",
                "line1": "1400 NW Example Ave",
                "city": "Miami",
                "state": "FL",
                "postal_code": "33125",
                "property_type": "house",
            },
        )
        client.post(
            reverse("web:request_help_step", kwargs={"step": "safety"}), {"hazards": ["none_known"]}
        )
        client.post(
            reverse("web:request_help_step", kwargs={"step": "reaching-you"}),
            {
                "full_name": "Doris Palmer",
                "phone": "(305) 555-0142",
                "no_email": "1",
                "availability": ["any_time"],
            },
        )
        # A successful step POST redirects forward -- re-render this step (as "Back" would)
        # to see the persisted `no_email` state reflected in the markup.
        resp = client.get(reverse("web:request_help_step", kwargs={"step": "reaching-you"}))
        html = resp.content.decode()
        locked_start = html.index('id="contact-pref-locked"')
        locked_tag_end = html.index(">", locked_start)
        assert "hidden" not in html[locked_start:locked_tag_end]
        fieldset_start = html.index('id="id_contact_preference"')
        fieldset_tag_end = html.index(">", fieldset_start)
        assert "hidden" in html[fieldset_start:fieldset_tag_end]
        assert "We&#x27;ll call you" in html or "We'll call you" in html

    def test_server_forces_phone_call_even_if_a_different_value_is_posted(self, client: Client):
        """The visible/locked UI is presentation only -- the real source of truth is
        `ham.requester_portal.forms.validate_intake_payload`, which already ignores whatever
        `contact_preference` a no-email submission carries."""
        _begin(client)
        client.post(
            reverse("web:request_help_step", kwargs={"step": "need"}),
            {"need_category": "roof_or_ceiling", "description": "Water leaks in."},
        )
        client.post(
            reverse("web:request_help_step", kwargs={"step": "home"}),
            {
                "relationship_to_property": "owner",
                "line1": "1400 NW Example Ave",
                "city": "Miami",
                "state": "FL",
                "postal_code": "33125",
                "property_type": "house",
            },
        )
        client.post(
            reverse("web:request_help_step", kwargs={"step": "safety"}), {"hazards": ["none_known"]}
        )
        client.post(
            reverse("web:request_help_step", kwargs={"step": "reaching-you"}),
            {
                "full_name": "Doris Palmer",
                "phone": "(305) 555-0142",
                "no_email": "1",
                "contact_preference": "email",  # a stale/tampered value
                "availability": ["any_time"],
            },
        )
        resp = client.get(reverse("web:request_help_step", kwargs={"step": "review"}))
        html = resp.content.decode()
        assert "We&#x27;ll call this number to confirm" in html or (
            "We'll call this number to confirm" in html
        )


class TestR6StepHeaderWording:
    def test_r6_says_step_5_of_5_not_last_step(self, client: Client):
        _begin(client)
        client.post(
            reverse("web:request_help_step", kwargs={"step": "need"}),
            {"need_category": "roof_or_ceiling", "description": "Water leaks in."},
        )
        client.post(
            reverse("web:request_help_step", kwargs={"step": "home"}),
            {
                "relationship_to_property": "owner",
                "line1": "1400 NW Example Ave",
                "city": "Miami",
                "state": "FL",
                "postal_code": "33125",
                "property_type": "house",
            },
        )
        client.post(
            reverse("web:request_help_step", kwargs={"step": "safety"}), {"hazards": ["none_known"]}
        )
        client.post(
            reverse("web:request_help_step", kwargs={"step": "reaching-you"}),
            {
                "full_name": "Doris Palmer",
                "phone": "(305) 555-0142",
                "email": "doris.p@example.org",
                "contact_preference": "email",
                "availability": ["any_time"],
            },
        )
        resp = client.get(reverse("web:request_help_step", kwargs={"step": "review"}))
        html = resp.content.decode()
        assert "Step 5 of 5" in html
        assert "Last step" not in html

    def test_need_step_says_step_1_of_5(self, client: Client):
        _begin(client)
        resp = client.get(reverse("web:request_help_step", kwargs={"step": "need"}))
        assert "Step 1 of 5" in resp.content.decode()
