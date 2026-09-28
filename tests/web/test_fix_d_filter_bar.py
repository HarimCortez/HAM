"""FIX-D item 7: spot-check the shared `.filter-bar` CSS change (`:has(.filter-bar__field)`,
added for L1's requests list) on the two other screens that reuse `.filter-bar` --
`audit_log_list.html` and `admin_users_list.html` -- and fix the regression it caused
(visual QA M16's "label orphans from its control" bug also applied to the audit log's visible
labels; `.filter-bar select, .filter-bar input { width: 100% }` at <768 forces every bare
select/input full width with nothing pairing it to its own label).
"""

from __future__ import annotations

import pytest
from django.urls import reverse

from ham.identity.models import RoleAssignment, SharedIdentityProfile
from ham.platform.clock import now as clock_now

pytestmark = pytest.mark.django_db


def _login(client, make_user, *, email: str, full_name: str, role: str):
    user = make_user(email)
    SharedIdentityProfile.objects.create(user=user, full_name=full_name)
    RoleAssignment.objects.create(user=user, role=role, granted_at=clock_now())
    client.force_login(user)
    session = client.session
    session["ham_mfa_satisfied"] = True
    session.save()
    return user


class TestAuditLogFilterBarFieldWrapping:
    def test_each_labelled_control_is_wrapped_in_filter_bar_field(self, client, make_user):
        _login(
            client,
            make_user,
            email="admin-fixd@example.org",
            full_name="Ada Admin",
            role="ADMINISTRATOR",
        )
        resp = client.get(reverse("web:audit_log"))
        assert resp.status_code == 200
        html = resp.content.decode()
        assert html.count('class="filter-bar__field"') == 7
        # Every field's label immediately precedes its own control inside one wrapper, so the
        # pair can never separate onto different rows (M16).
        for label_id, control_id in [
            ("id_range", "id_range"),
            ("id_from", "id_from"),
            ("id_to", "id_to"),
            ("id_user_q", "id_user_q"),
            ("id_project", "id_project"),
            ("id_action", "id_action"),
            ("id_role", "id_role"),
        ]:
            label_pos = html.index(f'for="{label_id}"')
            control_pos = html.index(f'id="{control_id}"', label_pos)
            wrapper_start = html.rindex('class="filter-bar__field"', 0, label_pos)
            wrapper_close = html.index("</div>", control_pos)
            assert wrapper_start < label_pos < control_pos < wrapper_close


class TestAdminUsersFilterBarUnaffected:
    def test_filter_bar_still_renders_and_labels_are_visually_hidden(self, client, make_user):
        """`admin_users_list.html` never separated its (visually-hidden) labels from their
        controls, so it doesn't need the `.filter-bar__field` treatment -- this just confirms
        the shared CSS change didn't regress it (still one plain `.filter-bar` with the same
        three controls, 200 OK)."""
        _login(
            client,
            make_user,
            email="admin-fixd2@example.org",
            full_name="Ada Admin",
            role="ADMINISTRATOR",
        )
        resp = client.get(reverse("web:admin_users"))
        assert resp.status_code == 200
        html = resp.content.decode()
        assert 'class="filter-bar"' in html
        assert 'id="id_q"' in html
        assert 'id="id_role"' in html
        assert 'id="id_status"' in html
        assert 'class="visually-hidden" for="id_q"' in html
