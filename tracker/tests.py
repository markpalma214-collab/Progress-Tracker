from datetime import datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo

from allauth.account.models import EmailAddress
from allauth.core import context as allauth_context
from allauth.socialaccount.adapter import get_adapter
from allauth.socialaccount.helpers import complete_social_login
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.contrib.auth import get_user_model
from django.contrib.auth.middleware import AuthenticationMiddleware
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import services
from .models import Presence, Profile, Reward, Task

User = get_user_model()
MANILA = ZoneInfo("Asia/Manila")
NOW = datetime(2026, 9, 16, 12, 0, tzinfo=MANILA)  # a Wednesday, fixed for stable tests


def make_user(name, **extra):
    return User.objects.create_user(name, password="s3cret-pass!", **extra)


def make_task(user, title="Study", duration=25, **extra):
    return Task.objects.create(user=user, title=title, duration=duration, **extra)


def make_session(user, completed_at, seconds, **extra):
    """A finished session ending at ``completed_at`` that lasted ``seconds``."""
    return Task.objects.create(
        user=user,
        title=extra.pop("title", "Session"),
        duration=max(1, seconds // 60),
        started_at=completed_at - timedelta(seconds=seconds),
        completed_at=completed_at,
        studied_seconds=seconds,
        is_completed=True,
        **extra,
    )


class ModelTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")

    def test_task_creation_does_not_start_the_timer(self):
        task = make_task(self.alice)
        self.assertIsNone(task.started_at)
        self.assertIsNone(task.completed_at)
        self.assertFalse(task.is_completed)
        self.assertEqual(task.status, "pending")

    def test_task_belongs_to_user_and_is_deleted_with_them(self):
        make_task(self.alice, "One")
        make_task(self.alice, "Two")
        self.assertEqual(self.alice.tasks.count(), 2)
        self.alice.delete()
        self.assertEqual(Task.objects.count(), 0)

    def test_reward_creation_and_cascade(self):
        task = make_task(self.alice)
        Reward.objects.create(task=task, reward="Bubble tea")
        Reward.objects.create(task=task, reward="Episode of anime")
        self.assertEqual(task.rewards.count(), 2)
        task.delete()
        self.assertEqual(Reward.objects.count(), 0)

    def test_database_allows_only_one_running_task_per_user(self):
        Task.objects.create(user=self.alice, title="A", duration=10, started_at=NOW)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Task.objects.create(user=self.alice, title="B", duration=10, started_at=NOW)

    def test_progress_calculation(self):
        task = Task(user=self.alice, title="T", duration=60, started_at=NOW - timedelta(minutes=30))
        self.assertEqual(task.progress_percent(NOW), 50)
        self.assertEqual(task.remaining_seconds(NOW), 30 * 60)
        late = Task(user=self.alice, title="T", duration=60, started_at=NOW - timedelta(hours=5))
        self.assertEqual(late.progress_percent(NOW), 100)  # never above 100
        self.assertEqual(late.remaining_seconds(NOW), 0)
        self.assertEqual(Task(user=self.alice, title="T", duration=60).progress_percent(NOW), 0)


class AuthenticationTests(TestCase):
    def test_anonymous_users_are_redirected_to_login(self):
        task = make_task(make_user("owner"))
        urls = [
            reverse("dashboard"),
            reverse("task_list"),
            reverse("task_create"),
            reverse("task_detail", args=[task.pk]),
            reverse("history"),
            reverse("subjects"),
            reverse("rankings"),
            reverse("rankings_period", args=["week"]),
            reverse("user_progress", args=["owner"]),
            reverse("rewards"),
            reverse("profile"),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertRedirects(
                    self.client.get(url), f"{reverse('account_login')}?next={url}", fetch_redirect_response=False
                )

    def test_anonymous_cannot_use_timer_endpoints(self):
        task = make_task(make_user("owner"))
        for name in ("task_start", "task_stop"):
            response = self.client.post(reverse(name, args=[task.pk]))
            self.assertEqual(response.status_code, 302)
            self.assertIn(reverse("account_login"), response.url)
        task.refresh_from_db()
        self.assertIsNone(task.started_at)

    def test_login_and_signup_pages_render(self):
        self.assertEqual(self.client.get(reverse("account_login")).status_code, 200)
        self.assertEqual(self.client.get(reverse("account_signup")).status_code, 200)

    def test_logged_in_user_sees_every_page(self):
        user = make_user("alice")
        task = make_task(user)
        make_session(user, timezone.now(), 600)
        self.client.force_login(user)
        for name, args in [
            ("dashboard", []), ("task_list", []), ("task_create", []), ("task_detail", [task.pk]),
            ("history", []), ("subjects", []), ("rankings", []), ("rankings_period", ["today"]),
            ("user_progress", ["alice"]), ("rewards", []), ("profile", []),
        ]:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 200)


class PermissionTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        self.bobs_task = make_task(self.bob, "Bob's task")
        self.client.force_login(self.alice)

    def test_cannot_start_another_users_task(self):
        response = self.client.post(reverse("task_start", args=[self.bobs_task.pk]))
        self.assertEqual(response.status_code, 404)
        self.bobs_task.refresh_from_db()
        self.assertIsNone(self.bobs_task.started_at)

    def test_cannot_stop_another_users_task(self):
        running = Task.objects.create(user=self.bob, title="Running", duration=30, started_at=timezone.now())
        response = self.client.post(reverse("task_stop", args=[running.pk]))
        self.assertEqual(response.status_code, 404)
        running.refresh_from_db()
        self.assertIsNone(running.completed_at)
        self.assertFalse(running.is_completed)

    def test_cannot_view_or_delete_another_users_task(self):
        self.assertEqual(self.client.get(reverse("task_detail", args=[self.bobs_task.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("task_delete", args=[self.bobs_task.pk])).status_code, 404)
        self.assertTrue(Task.objects.filter(pk=self.bobs_task.pk).exists())

    def test_cannot_attach_reward_to_another_users_task(self):
        response = self.client.post(reverse("rewards"), {"task": self.bobs_task.pk, "reward": "Hack"})
        self.assertEqual(response.status_code, 200)  # form re-rendered with an error
        self.assertFalse(Reward.objects.exists())

    def test_state_changes_require_post(self):
        mine = make_task(self.alice)
        self.assertEqual(self.client.get(reverse("task_start", args=[mine.pk])).status_code, 405)
        self.assertEqual(self.client.get(reverse("task_stop", args=[mine.pk])).status_code, 405)
        self.assertEqual(self.client.get(reverse("task_delete", args=[mine.pk])).status_code, 405)

    def test_new_task_always_belongs_to_the_logged_in_user(self):
        self.client.post(reverse("task_create"), {"title": "Mine", "duration": 20, "break_duration": 5, "user": self.bob.pk})
        self.assertEqual(Task.objects.get(title="Mine").user, self.alice)


class TaskFormTests(TestCase):
    def setUp(self):
        self.client.force_login(make_user("alice"))

    def test_valid_task_is_created_but_not_started(self):
        response = self.client.post(
            reverse("task_create"), {"title": "  Django  ", "description": "", "duration": 45, "break_duration": 5}
        )
        self.assertRedirects(response, reverse("dashboard"))
        task = Task.objects.get()
        self.assertEqual(task.title, "Django")
        self.assertIsNone(task.started_at)

    def test_invalid_input_is_rejected(self):
        for data in (
            {"title": "", "duration": 25, "break_duration": 5},
            {"title": "   ", "duration": 25, "break_duration": 5},
            {"title": "X", "duration": 0, "break_duration": 5},
            {"title": "X", "duration": "abc", "break_duration": 5},
            {"title": "X", "duration": -5, "break_duration": 5},
        ):
            with self.subTest(data=data):
                self.assertEqual(self.client.post(reverse("task_create"), data).status_code, 200)
        self.assertEqual(Task.objects.count(), 0)


class TimerTests(TestCase):
    def setUp(self):
        self.user = make_user("alice")
        self.task = make_task(self.user, duration=25)
        self.client.force_login(self.user)

    def test_start_sets_started_at(self):
        response = self.client.post(reverse("task_start", args=[self.task.pk]))
        self.assertRedirects(response, reverse("dashboard"))
        self.task.refresh_from_db()
        self.assertIsNotNone(self.task.started_at)
        self.assertTrue(self.task.is_running)

    def test_only_one_active_timer_per_user(self):
        second = make_task(self.user, "Second")
        self.client.post(reverse("task_start", args=[self.task.pk]))
        response = self.client.post(reverse("task_start", args=[second.pk]), follow=True)
        second.refresh_from_db()
        self.assertIsNone(second.started_at)
        self.assertContains(response, "already have a running timer")

    def test_stop_records_completion_and_study_time(self):
        started = NOW - timedelta(minutes=10)
        services.start_task(self.task, now=started)
        task = services.stop_task(self.task, now=NOW)
        self.assertEqual(task.completed_at, NOW)
        self.assertEqual(task.studied_seconds, 600)
        self.assertTrue(task.is_completed)
        self.assertEqual(task.status, "stopped")  # stopped early
        self.assertEqual(task.break_ends_at, NOW + timedelta(minutes=task.break_duration))

    def test_late_stop_is_capped_at_the_planned_duration(self):
        services.start_task(self.task, now=NOW - timedelta(hours=3))
        task = services.stop_task(self.task, now=NOW)
        self.assertEqual(task.studied_seconds, 25 * 60)  # an open tab can't inflate study time
        self.assertEqual(task.status, "completed")
        self.assertTrue(task.rewards.filter(reward="Session complete").exists())

    def test_expired_sessions_are_finalized_by_the_server(self):
        services.start_task(self.task, now=NOW - timedelta(hours=2))
        services.finalize_expired(now=NOW)
        self.task.refresh_from_db()
        self.assertTrue(self.task.is_completed)
        self.assertEqual(self.task.studied_seconds, 25 * 60)

    def test_stopping_twice_is_rejected(self):
        services.start_task(self.task, now=NOW - timedelta(minutes=5))
        services.stop_task(self.task, now=NOW)
        with self.assertRaises(services.TimerError):
            services.stop_task(self.task, now=NOW)

    def test_ajax_stop_returns_json(self):
        self.client.post(reverse("task_start", args=[self.task.pk]))
        response = self.client.post(reverse("task_stop", args=[self.task.pk]), HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        again = self.client.post(reverse("task_stop", args=[self.task.pk]), HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(again.status_code, 409)

    def test_dashboard_wires_the_timer_to_the_stop_endpoint(self):
        self.client.post(reverse("task_start", args=[self.task.pk]))
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "data-timer")
        self.assertContains(response, f'data-stop-url="{reverse("task_stop", args=[self.task.pk])}"')

    def test_break_state_is_derived_from_completion_time(self):
        task = make_session(self.user, NOW, 600, break_duration=5)
        self.assertTrue(task.in_break(NOW + timedelta(minutes=4)))
        self.assertFalse(task.in_break(NOW + timedelta(minutes=6)))


class StatsTests(TestCase):
    def test_dashboard_counts(self):
        user = make_user("alice")
        make_task(user, "Pending")
        make_session(user, NOW, 1800)
        Task.objects.create(user=user, title="Running", duration=30, started_at=NOW)
        with timezone.override(MANILA):
            stats = services.dashboard_stats(user, now=NOW)
        self.assertEqual(
            (stats["total"], stats["completed"], stats["active"], stats["remaining"]), (3, 1, 1, 1)
        )
        self.assertEqual(stats["study_seconds"], 1800)
        self.assertEqual(stats["today_seconds"], 1800)


class RankingTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        d = lambda *args, **kw: datetime(*args, tzinfo=MANILA, **kw)
        make_session(self.alice, d(2026, 9, 16, 9), 1800)    # today
        make_session(self.alice, d(2026, 9, 14, 10), 3600)   # Monday: this week
        make_session(self.alice, d(2026, 9, 2, 10), 7200)    # this month
        make_session(self.alice, d(2026, 8, 20, 10), 5400)   # this year
        make_session(self.alice, d(2025, 12, 31, 23, 59), 900)  # last year
        make_session(self.bob, d(2026, 9, 16, 8), 600)       # today
        Task.objects.create(user=self.bob, title="Running", duration=30, started_at=NOW)  # never counted

    def totals(self, period):
        with timezone.override(MANILA):
            return {row["user"].username: row["seconds"] for row in services.leaderboard(period, now=NOW)}

    def test_study_time_is_aggregated_per_period(self):
        self.assertEqual(self.totals("today"), {"alice": 1800, "bob": 600})
        self.assertEqual(self.totals("week"), {"alice": 5400, "bob": 600})
        self.assertEqual(self.totals("month"), {"alice": 12600, "bob": 600})
        self.assertEqual(self.totals("year"), {"alice": 18000, "bob": 600})
        self.assertEqual(self.totals("all"), {"alice": 18900, "bob": 600})

    def test_ordering_and_shared_ranks_for_ties(self):
        carol = make_user("carol")
        make_session(carol, datetime(2026, 9, 16, 7, tzinfo=MANILA), 600)
        with timezone.override(MANILA):
            rows = services.leaderboard("today", now=NOW)
        self.assertEqual([(r["user"].username, r["rank"]) for r in rows], [("alice", 1), ("bob", 2), ("carol", 2)])

    def test_today_follows_the_configured_timezone_not_utc(self):
        # 23:30 UTC on the 15th is 07:30 on the 16th in Manila -> "today"; 15:59 UTC is 23:59 on the 15th.
        make_session(self.bob, datetime(2026, 9, 15, 23, 30, tzinfo=dt_timezone.utc), 300)
        make_session(self.bob, datetime(2026, 9, 15, 15, 59, tzinfo=dt_timezone.utc), 300)
        self.assertEqual(self.totals("today")["bob"], 900)

    def test_subject_breakdown_groups_by_category_then_title(self):
        make_session(self.alice, datetime(2026, 9, 15, 9, tzinfo=MANILA), 3600, category="Python", title="Loops")
        make_session(self.alice, datetime(2026, 9, 15, 11, tzinfo=MANILA), 1800, category="Python", title="Classes")
        make_session(self.alice, datetime(2026, 9, 1, 11, tzinfo=MANILA), 900, title="Japanese")
        with timezone.override(MANILA):
            week = services.subject_breakdown(self.alice, "7d", now=NOW)
            everything = services.subject_breakdown(self.alice, "all", now=NOW)
        self.assertEqual([(r["label"], r["seconds"], r["sessions"]) for r in week[:1]], [("Python", 5400, 2)])
        self.assertIn("Japanese", [r["label"] for r in everything])
        self.assertNotIn("Japanese", [r["label"] for r in week])

    def test_ranking_pages(self):
        self.client.force_login(self.alice)
        self.assertContains(self.client.get(reverse("rankings")), "bob")
        self.assertEqual(self.client.get(reverse("rankings_period", args=["decade"])).status_code, 404)


class PrivacyTests(TestCase):
    def test_other_users_see_only_public_information(self):
        alice = make_user("alice")
        bob = make_user("bob", email="bob@example.com")
        Task.objects.create(
            user=bob, title="Secret exam prep", description="private notes", duration=30,
            started_at=timezone.now(), is_public=False,
        )
        make_session(bob, timezone.now(), 600, title="Public reading", is_public=True)
        make_session(bob, timezone.now(), 600, title="Hidden essay", is_public=False)
        self.client.force_login(alice)
        response = self.client.get(reverse("user_progress", args=["bob"]))
        self.assertContains(response, "Private session")
        self.assertContains(response, "Public reading")
        for secret in ("Secret exam prep", "private notes", "Hidden essay", "bob@example.com"):
            self.assertNotContains(response, secret)

    def test_owner_sees_their_own_private_titles(self):
        bob = make_user("bob")
        make_session(bob, timezone.now(), 600, title="Hidden essay", is_public=False)
        self.client.force_login(bob)
        self.assertContains(self.client.get(reverse("user_progress", args=["bob"])), "Hidden essay")


class PresenceTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")

    def test_touch_presence_is_throttled(self):
        session = {}
        self.assertTrue(services.touch_presence(self.alice, session, now=NOW))
        self.assertFalse(services.touch_presence(self.alice, session, now=NOW + timedelta(seconds=10)))
        self.assertEqual(self.alice.presence.last_seen, NOW)  # not rewritten
        self.assertTrue(services.touch_presence(self.alice, session, now=NOW + timedelta(seconds=60)))
        self.alice.presence.refresh_from_db()
        self.assertEqual(self.alice.presence.last_seen, NOW + timedelta(seconds=60))
        self.assertEqual(Presence.objects.filter(user=self.alice).count(), 1)

    def test_online_means_seen_within_the_active_window(self):
        Presence.objects.create(user=self.alice, last_seen=NOW - timedelta(seconds=90))
        Presence.objects.create(user=self.bob, last_seen=NOW - timedelta(minutes=3))
        self.assertEqual(services.presence_counts(NOW)["online"], 1)
        carol = make_user("carol")
        carol.is_active = False
        carol.save()
        Presence.objects.create(user=carol, last_seen=NOW)
        self.assertEqual(services.presence_counts(NOW)["online"], 1)  # inactive users never count

    def test_studying_counts_running_timers_only(self):
        Task.objects.create(user=self.alice, title="Now", duration=60, started_at=NOW - timedelta(minutes=5))
        make_task(self.bob)  # pending
        make_session(self.bob, NOW, 600)  # finished
        self.assertEqual(services.presence_counts(NOW)["studying"], 1)

    def test_expired_timers_do_not_count_as_studying(self):
        Task.objects.create(user=self.alice, title="Old", duration=25, started_at=NOW - timedelta(hours=3))
        self.assertEqual(services.presence_counts(NOW)["studying"], 0)

    def test_middleware_records_logged_in_visits_only(self):
        self.client.get(reverse("account_login"))
        self.assertFalse(Presence.objects.exists())
        self.client.force_login(self.alice)
        self.client.get(reverse("dashboard"))
        self.assertTrue(Presence.objects.filter(user=self.alice).exists())
        self.assertFalse(Presence.objects.filter(user=self.bob).exists())

    def test_dashboard_shows_the_online_count(self):
        self.client.force_login(self.alice)
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "data-online")
        self.assertEqual(response.context["presence"]["online"], 1)

    def test_ping_returns_counts_and_requires_post_and_login(self):
        url = reverse("presence_ping")
        anonymous = self.client.post(url)
        self.assertEqual(anonymous.status_code, 401)  # JSON error, not a redirect to the login page
        self.client.force_login(self.alice)
        self.assertEqual(self.client.get(url).status_code, 405)
        data = self.client.post(url).json()
        self.assertEqual(data, {"online": 1, "studying": 0})


class LiveRoomTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        now = timezone.now()
        Task.objects.create(user=self.alice, title="Alice public", duration=30, started_at=now - timedelta(minutes=3))
        Task.objects.create(
            user=self.bob, title="Bob secret", duration=45, started_at=now - timedelta(minutes=1), is_public=False
        )
        self.client.force_login(self.alice)

    def test_page_renders_with_the_data_url(self):
        response = self.client.get(reverse("live"))
        self.assertContains(response, f'data-live-url="{reverse("live_data")}"')

    def test_live_data_lists_running_timers_and_hides_private_titles(self):
        data = self.client.get(reverse("live_data")).json()
        by_user = {s["username"]: s for s in data["sessions"]}
        self.assertEqual(set(by_user), {"alice", "bob"})
        self.assertEqual(by_user["alice"]["title"], "Alice public")
        self.assertTrue(by_user["alice"]["is_me"])
        self.assertEqual(by_user["bob"]["title"], "Private session")
        self.assertFalse(by_user["bob"]["is_me"])
        self.assertEqual(by_user["bob"]["duration"], 45 * 60)
        self.assertEqual(by_user["bob"]["url"], reverse("user_progress", args=["bob"]))
        self.assertEqual(data["studying"], 2)
        self.assertIn("now", data)
        self.assertNotIn("Bob secret", str(data))

    def test_the_owner_sees_their_own_private_title(self):
        self.client.force_login(self.bob)
        by_user = {s["username"]: s for s in self.client.get(reverse("live_data")).json()["sessions"]}
        self.assertEqual(by_user["bob"]["title"], "Bob secret")

    def test_finished_timers_disappear(self):
        Task.objects.filter(user=self.bob).update(started_at=timezone.now() - timedelta(hours=3))
        usernames = [s["username"] for s in self.client.get(reverse("live_data")).json()["sessions"]]
        self.assertEqual(usernames, ["alice"])

    def test_live_data_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("live_data")).status_code, 401)


GOOGLE_TEST_SETTINGS = {"google": {"APP": {"client_id": "test-id", "secret": "test-secret", "key": ""}}}


def make_new_oauth_user(username="player_1a2b3c4d"):
    """A user exactly as the OAuth signup creates them: placeholder name + pending flag."""
    user = make_user(username)
    Profile.objects.create(user=user, needs_username=True)
    return user


class OAuthSignupTests(TestCase):
    """Drives django-allauth's real social signup pipeline with a fake Google profile."""

    def google_signup(self, email="jane.doe@gmail.com", first="Jane", last="Doe", uid="1234567890"):
        request = RequestFactory().get("/accounts/google/login/callback/")
        noop = lambda r: None
        SessionMiddleware(noop).process_request(request)
        MessageMiddleware(noop).process_request(request)
        AuthenticationMiddleware(noop).process_request(request)
        request.session.save()
        account = SocialAccount(provider="google", uid=uid, extra_data={"email": email})
        provider = get_adapter(request).get_provider(request, "google")
        sociallogin = SocialLogin(
            user=User(), account=account, provider=provider,
            email_addresses=[EmailAddress(email=email, verified=True, primary=True)],
        )
        get_adapter(request).populate_user(request, sociallogin, {"email": email, "first_name": first, "last_name": last})
        with allauth_context.request_context(request):
            complete_social_login(request, sociallogin)
        return request

    @override_settings(SOCIALACCOUNT_PROVIDERS=GOOGLE_TEST_SETTINGS)
    def test_google_signup_never_uses_the_gmail_name(self):
        request = self.google_signup()
        user = User.objects.get(email="jane.doe@gmail.com")
        self.assertRegex(user.username, r"^player_[0-9a-f]{8}$")
        self.assertNotIn("jane", user.username.lower())
        self.assertNotIn("doe", user.username.lower())
        self.assertTrue(user.profile.needs_username)
        self.assertFalse(user.has_usable_password())
        self.assertEqual(request.session["_auth_user_id"], str(user.pk))  # signed in straight away

    @override_settings(SOCIALACCOUNT_PROVIDERS=GOOGLE_TEST_SETTINGS)
    def test_two_google_signups_get_different_placeholders(self):
        self.google_signup(email="a@gmail.com", uid="1")
        self.google_signup(email="b@gmail.com", uid="2")
        names = set(User.objects.values_list("username", flat=True))
        self.assertEqual(len(names), 2)

    def test_password_signups_are_not_asked_for_a_username(self):
        user = make_user("regular")
        self.client.force_login(user)
        self.assertNotContains(self.client.get(reverse("dashboard")), "username-modal")


class UsernameSetupTests(TestCase):
    def setUp(self):
        self.user = make_new_oauth_user()
        self.client.force_login(self.user)

    def choose(self, name, **extra):
        return self.client.post(reverse("username_set"), {"username": name}, **extra)

    def test_popup_is_on_the_dashboard(self):
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, 'id="username-modal"')
        self.assertContains(response, 'aria-modal="true"')
        self.assertContains(response, reverse("username_set"))

    def test_other_pages_redirect_to_the_dashboard_until_a_name_is_chosen(self):
        for name in ("task_list", "task_create", "history", "rankings", "live", "rewards", "profile", "subjects"):
            with self.subTest(page=name):
                self.assertRedirects(self.client.get(reverse(name)), reverse("dashboard"), fetch_redirect_response=False)
        task = make_task(self.user)
        self.assertRedirects(
            self.client.post(reverse("task_start", args=[task.pk])), reverse("dashboard"), fetch_redirect_response=False
        )
        task.refresh_from_db()
        self.assertIsNone(task.started_at)

    def test_heartbeat_and_logout_still_work(self):
        self.assertEqual(self.client.post(reverse("presence_ping")).status_code, 200)
        response = self.client.post(reverse("account_logout"))
        self.assertNotEqual(response.url, reverse("dashboard"))

    def test_choosing_a_username_unlocks_the_site(self):
        response = self.choose("Focus_Fox")
        self.assertRedirects(response, reverse("dashboard"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "Focus_Fox")
        self.assertFalse(self.user.profile.needs_username)
        self.assertEqual(self.client.get(reverse("task_list")).status_code, 200)
        self.assertNotContains(self.client.get(reverse("dashboard")), "username-modal")

    def test_ajax_success_and_failure(self):
        bad = self.choose("x", HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(bad.status_code, 400)
        self.assertIn("username", bad.json()["errors"])
        good = self.choose("night_owl", HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(good.json(), {"ok": True})

    def test_invalid_usernames_are_rejected(self):
        make_user("Taken_Name")
        for bad in ("ab", "a" * 21, "has space", "emoji😀name", "semi;colon", "admin", "ADMIN", "taken_name", "TAKEN_NAME"):
            with self.subTest(name=bad):
                response = self.choose(bad, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
                self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "player_1a2b3c4d")
        self.assertTrue(self.user.profile.needs_username)

    def test_username_cannot_be_changed_once_set(self):
        self.choose("first_choice")
        response = self.choose("second_choice", HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 403)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "first_choice")

    def test_anonymous_cannot_set_a_username(self):
        self.client.logout()
        response = self.choose("sneaky")
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("account_login"), response.url)


class LeaderboardUsernameTests(TestCase):
    def test_rankings_show_the_chosen_username_and_hide_placeholders(self):
        chosen = make_new_oauth_user()
        make_session(chosen, timezone.now(), 1200)
        pending = make_new_oauth_user("player_deadbeef")
        make_session(pending, timezone.now(), 3000)
        with timezone.override(MANILA):
            names = [row["user"].username for row in services.leaderboard("all")]
        self.assertEqual(names, [])  # nobody has chosen a name yet

        self.client.force_login(chosen)
        self.client.post(reverse("username_set"), {"username": "Focus_Fox"})
        page = self.client.get(reverse("rankings"))
        self.assertContains(page, "Focus_Fox")
        self.assertNotContains(page, "player_1a2b3c4d")
        self.assertNotContains(page, "player_deadbeef")
        self.assertContains(page, reverse("user_progress", args=["Focus_Fox"]))
