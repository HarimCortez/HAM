"""FIX-3A decision panel: security M1-M3 / UX M2 (Q-181, "pending" is a fact about the
decision, true for every viewer -- not just the decider) and visual QA M2 (take-over
reachability from the request page for another active pastor on a Reconsideration Pending
request).
"""

from __future__ import annotations

import pytest
from django.urls import reverse

from ham.identity.models import RoleAssignment
from ham.platform.clock import now as clock_now
from ham.requests.services_decisions import reject_request, request_reconsideration
from tests.web.test_s36_leadership_screens import _ctx_for, _login, _make_request

pytestmark = pytest.mark.django_db


class TestUndoWindowPendingForEveryViewer:
    def test_other_pastor_sees_pending_not_the_decided_state(self, client, make_user):
        req = _make_request()
        deciding_pastor = _login(
            client, make_user, email="ruth@example.org", full_name="Ruth A", role="PASTOR"
        )
        approve_response = self._approve(deciding_pastor, req)
        assert approve_response.stage == "initial"

        other_pastor = make_user("david@example.org")
        RoleAssignment.objects.create(user=other_pastor, role="PASTOR", granted_at=clock_now())
        client.logout()
        client.force_login(other_pastor)
        session = client.session
        session["ham_mfa_satisfied"] = True
        session.save()

        response = client.get(reverse("web:request_detail", args=[req.id]))
        body = response.content.decode()
        assert "Pending: Ruth A" in body
        # Not offered the "Undo decision..." action (that's the decider's own).
        assert "Undo decision" not in body
        # And not told "Next: site assessment" while the decision could still vanish.
        assert "Next: site assessment" not in body

    @staticmethod
    def _approve(user, req):
        from ham.requests.services_decisions import approve_request

        return approve_request(_ctx_for(user, "PASTOR"), request_id=req.id, route="pastoral")


class TestVisualM2TakeoverReachability:
    def test_another_active_pastor_sees_a_take_over_route_in(self, client, make_user):
        req = _make_request()
        original = _login(
            client, make_user, email="ruth@example.org", full_name="Ruth A", role="PASTOR"
        )
        approval = reject_request(
            _ctx_for(original, "PASTOR"),
            request_id=req.id,
            route="pastoral",
            reason_code="another_reason",
            message="Sorry",
        )
        req.refresh_from_db()
        from ham.platform.clock import FixedClock, set_clock

        set_clock(FixedClock(approval.effective_at))
        from ham.authz.context import RequesterContext

        request_reconsideration(RequesterContext(request_id=req.id))

        other_pastor = make_user("david@example.org")
        RoleAssignment.objects.create(user=other_pastor, role="PASTOR", granted_at=clock_now())
        client.logout()
        client.force_login(other_pastor)
        session = client.session
        session["ham_mfa_satisfied"] = True
        session.save()

        response = client.get(reverse("web:request_detail", args=[req.id]))
        body = response.content.decode()
        assert "Take over and approve" in body
        assert "Take over and decline" in body
