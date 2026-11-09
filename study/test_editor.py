from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse

from .models import Flashcard, Source


class FlashcardEditorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.source = Source.objects.create(
            title="Желілік хаттамалар",
            text="DNS атауды IP-адреске сәйкестендіреді.\nIP пакеттерді жеткізеді.",
            generation_mode="demo",
        )
        cls.other_source = Source.objects.create(
            title="Бөлек жинақ",
            text="Маршрутизатор пакеттерді желілер арасында тасымалдайды.",
            generation_mode="demo",
        )
        cls.neighbor = Flashcard.objects.create(
            source=cls.source,
            position=3,
            question="IP не істейді?",
            answer="Пакеттерді жеткізеді.",
            source_quote="IP пакеттерді жеткізеді.",
        )
        cls.card = Flashcard.objects.create(
            source=cls.source,
            position=1,
            question="DNS не істейді?",
            answer="Атауды IP-адреске сәйкестендіреді.",
            source_quote="DNS атауды IP-адреске сәйкестендіреді.",
            is_verified=True,
        )
        cls.other_card = Flashcard.objects.create(
            source=cls.other_source,
            position=1,
            question="Маршрутизатор не істейді?",
            answer="Пакеттерді желілер арасында тасымалдайды.",
            source_quote=cls.other_source.text,
            is_verified=True,
        )

    def setUp(self):
        self.detail_url = reverse("source_detail", kwargs={"pk": self.source.pk})
        self.edit_url = reverse("card_edit", kwargs={"pk": self.card.pk})
        self.delete_url = reverse("card_delete", kwargs={"pk": self.card.pk})
        self.review_url = reverse("card_review", kwargs={"pk": self.card.pk})

        generate_patcher = patch("study.views.generate_cards")
        self.generate_cards = generate_patcher.start()
        self.addCleanup(generate_patcher.stop)
        self.addCleanup(self.generate_cards.assert_not_called)

    def database_state(self):
        return (
            list(Source.objects.order_by("pk").values()),
            list(Flashcard.objects.order_by("pk").values()),
        )

    def edit_data(self, **overrides):
        data = {
            "question": "DNS атауды неге сәйкестендіреді?",
            "answer": "IP-адреске.",
            "source_quote": self.source.text,
        }
        data.update(overrides)
        return data

    def test_edit_get_displays_existing_values_without_writing(self):
        before = self.database_state()

        response = self.client.get(self.edit_url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "study/card_form.html")
        form = response.context["form"]
        self.assertFalse(form.is_bound)
        self.assertEqual(tuple(form.fields), ("question", "answer", "source_quote"))
        self.assertEqual(form.instance.pk, self.card.pk)
        self.assertEqual(form["question"].value(), self.card.question)
        self.assertEqual(form["answer"].value(), self.card.answer)
        self.assertEqual(form["source_quote"].value(), self.card.source_quote)
        self.assertEqual(self.database_state(), before)

    def test_valid_edit_updates_only_target_and_resets_verification(self):
        sources, cards = self.database_state()
        data = self.edit_data(source_quote=self.source.text.replace("\n", "\r\n"))
        expected_fields = {
            "question": data["question"],
            "answer": data["answer"],
            "source_quote": self.source.text,
            "is_verified": False,
        }

        response = self.client.post(self.edit_url, data)

        self.assertRedirects(response, self.detail_url, fetch_redirect_response=False)
        for card in cards:
            if card["id"] == self.card.pk:
                card.update(expected_fields)
        self.assertEqual(self.database_state(), (sources, cards))

    def test_invalid_edits_show_field_errors_and_do_not_write(self):
        cases = (
            ("question", ""),
            ("answer", ""),
            ("source_quote", ""),
            ("question", "С" * 301),
            ("source_quote", self.other_source.text),
        )
        before = self.database_state()

        for field, value in cases:
            with self.subTest(field=field, value=value):
                data = self.edit_data(**{field: value})
                response = self.client.post(self.edit_url, data)

                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, "study/card_form.html")
                form = response.context["form"]
                self.assertTrue(form.is_bound)
                self.assertIn(field, form.errors)
                self.assertContains(response, form.errors[field][0])
                for name, submitted_value in data.items():
                    self.assertEqual(form[name].value(), submitted_value)
                self.assertEqual(self.database_state(), before)

    def test_edit_ignores_posted_source_position_and_verification(self):
        response = self.client.post(
            self.edit_url,
            self.edit_data(source=self.other_source.pk, position=99, is_verified="1"),
        )

        self.assertRedirects(response, self.detail_url, fetch_redirect_response=False)
        self.card.refresh_from_db()
        self.assertEqual(self.card.question, self.edit_data()["question"])
        self.assertEqual(self.card.source_id, self.source.pk)
        self.assertEqual(self.card.position, 1)
        self.assertFalse(self.card.is_verified)

    def test_delete_confirmation_and_cancel_do_not_write(self):
        before = self.database_state()

        response = self.client.get(self.delete_url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "study/card_confirm_delete.html")
        self.assertContains(response, self.card.question)
        self.assertContains(response, "Иә, өшіру")
        self.assertContains(
            response,
            f'<a href="{self.detail_url}">Бас тарту</a>',
            html=True,
        )
        self.assertEqual(self.database_state(), before)

        self.assertEqual(self.client.get(self.detail_url).status_code, 200)
        self.assertEqual(self.database_state(), before)

    def test_delete_post_removes_only_target_without_renumbering(self):
        sources, cards = self.database_state()

        response = self.client.post(self.delete_url)

        self.assertRedirects(response, self.detail_url, fetch_redirect_response=False)
        remaining_cards = [card for card in cards if card["id"] != self.card.pk]
        self.assertEqual(self.database_state(), (sources, remaining_cards))

        detail = self.client.get(self.detail_url)
        self.assertEqual(detail.context["cards"], [self.neighbor])
        self.assertEqual(detail.context["cards"][0].position, 3)
        self.assert_counts(detail, total=1, verified=0, pending=1)

    def test_review_get_returns_405_without_writing(self):
        before = self.database_state()

        response = self.client.get(self.review_url)

        self.assertEqual(response.status_code, 405)
        self.assertEqual(self.database_state(), before)

    def test_review_reset_verify_and_repeated_verify_update_only_status(self):
        sources, cards = self.database_state()

        for action, expected in (
            ("reset", False),
            ("verify", True),
            ("verify", True),
        ):
            with self.subTest(action=action, expected=expected):
                response = self.client.post(self.review_url, {"action": action})

                self.assertRedirects(
                    response, self.detail_url, fetch_redirect_response=False
                )
                for card in cards:
                    if card["id"] == self.card.pk:
                        card["is_verified"] = expected
                self.assertEqual(self.database_state(), (sources, cards))

                detail = self.client.get(self.detail_url)
                self.assertEqual(detail.context["cards"][0].is_verified, expected)
                verified = int(expected)
                self.assert_counts(detail, total=2, verified=verified, pending=2 - verified)

    def test_invalid_or_missing_review_action_returns_400_without_writing(self):
        before = self.database_state()

        for data in ({"action": "toggle"}, {}):
            with self.subTest(data=data):
                response = self.client.post(self.review_url, data)

                self.assertEqual(response.status_code, 400)
                self.assertEqual(self.database_state(), before)

    def assert_counts(self, response, *, total, verified, pending):
        self.assertEqual(response.context["total_count"], total)
        self.assertEqual(response.context["verified_count"], verified)
        self.assertEqual(response.context["pending_count"], pending)

    def test_filters_show_only_source_cards_and_keep_collection_counts(self):
        cases = (
            ({}, "all", [self.card, self.neighbor]),
            ({"status": "all"}, "all", [self.card, self.neighbor]),
            ({"status": "pending"}, "pending", [self.neighbor]),
            ({"status": "verified"}, "verified", [self.card]),
            ({"status": "unknown"}, "all", [self.card, self.neighbor]),
        )
        before = self.database_state()

        for query, status, expected_cards in cases:
            with self.subTest(query=query):
                response = self.client.get(self.detail_url, query)

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["source"], self.source)
                self.assertEqual(response.context["status"], status)
                self.assertEqual(response.context["cards"], expected_cards)
                self.assert_counts(response, total=2, verified=1, pending=1)
                self.assertContains(response, 'aria-current="page"', count=1)
                self.assertNotContains(response, self.other_card.question)
                for card in expected_cards:
                    self.assertContains(response, card.question)
                for card in (self.card, self.neighbor):
                    if card not in expected_cards:
                        self.assertNotContains(response, card.question)
                self.assertEqual(self.database_state(), before)

    def test_empty_filter_offers_link_to_all_cards(self):
        self.source.cards.update(is_verified=True)
        before = self.database_state()

        response = self.client.get(self.detail_url, {"status": "pending"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["cards"], [])
        self.assert_counts(response, total=2, verified=2, pending=0)
        self.assertContains(response, "Бұл сүзгіге сәйкес карточка жоқ.")
        self.assertContains(
            response,
            f'<a href="{self.detail_url}">Барлығын көрсету</a>',
            html=True,
        )
        self.assertEqual(self.database_state(), before)

    def test_empty_collection_displays_saved_source_text(self):
        self.source.cards.all().delete()
        before = self.database_state()

        response = self.client.get(self.detail_url, {"status": "verified"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["cards"], [])
        self.assert_counts(response, total=0, verified=0, pending=0)
        self.assertContains(response, "Бұл жинақта карточка қалмады.")
        self.assertContains(response, '<details class="editor" open>')
        for line in self.source.text.splitlines():
            self.assertContains(response, line)
        self.assertEqual(self.database_state(), before)

    def test_missing_source_and_card_return_404(self):
        missing_source_pk = max(self.source.pk, self.other_source.pk) + 1
        missing_card_pk = max(self.card.pk, self.neighbor.pk, self.other_card.pk) + 1
        before = self.database_state()
        cases = (
            ("get", "source_detail", missing_source_pk, {}),
            ("get", "card_edit", missing_card_pk, {}),
            ("post", "card_edit", missing_card_pk, self.edit_data()),
            ("get", "card_delete", missing_card_pk, {}),
            ("post", "card_delete", missing_card_pk, {}),
            ("post", "card_review", missing_card_pk, {"action": "verify"}),
        )

        for method, route, pk, data in cases:
            with self.subTest(method=method, route=route):
                url = reverse(route, kwargs={"pk": pk})
                response = getattr(self.client, method)(url, data)

                self.assertEqual(response.status_code, 404)
                self.assertEqual(self.database_state(), before)

    def test_post_without_csrf_token_is_rejected_without_writing(self):
        csrf_client = Client(enforce_csrf_checks=True)
        before = self.database_state()
        cases = (
            (self.edit_url, self.edit_data()),
            (self.delete_url, {}),
            (self.review_url, {"action": "reset"}),
        )

        for url, data in cases:
            with self.subTest(url=url):
                response = csrf_client.post(url, data)

                self.assertEqual(response.status_code, 403)
                self.assertEqual(self.database_state(), before)