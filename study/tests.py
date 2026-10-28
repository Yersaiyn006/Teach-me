
from copy import deepcopy
from unittest.mock import patch

from django.db import DatabaseError
from django.test import TestCase, override_settings
from django.urls import reverse

from .demo import DEMO_TEXT, DEMO_CARDS
from .models import Source, Flashcard
from .services import GenerationError, validate_cards


@override_settings(TEACHME_MODE="demo")
class TeachMeTests(TestCase):

    def setUp(self):
        self.home_url = reverse("home")
        self.title = "Компьютерлік желілер"

    def post_data(self, text=DEMO_TEXT):
        return {
            "title": self.title,
            "text": text,
        }

    def assert_database_empty(self):
        self.assertEqual(Source.objects.count(), 0)
        self.assertEqual(Flashcard.objects.count(), 0)

    def test_valid_demo_post_redirects_and_saves_all_cards(self):
        with patch(
            "study.services._gemini_urllib_adapter"
        ) as provider:
            response = self.client.post(
                self.home_url,
                data=self.post_data(),
            )

        provider.assert_not_called()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Source.objects.count(), 1)
        self.assertEqual(Flashcard.objects.count(), 3)

        source = Source.objects.get()

        self.assertEqual(
            response.url,
            reverse("source_detail", kwargs={"pk": source.pk}),
        )
        self.assertEqual(source.title, self.title)
        self.assertEqual(source.text, DEMO_TEXT)
        self.assertEqual(source.generation_mode, "demo")

        saved_cards = list(
            source.cards.order_by("position", "id")
        )

        self.assertEqual(
            [card.position for card in saved_cards],
            [1, 2, 3],
        )

        for saved, expected in zip(saved_cards, DEMO_CARDS):
            self.assertEqual(
                saved.question,
                expected["question"],
            )
            self.assertEqual(
                saved.answer,
                expected["answer"],
            )
            self.assertEqual(
                saved.source_quote,
                expected["source_quote"],
            )

    def test_short_text_does_not_call_provider(self):
        with patch(
            "study.views.generate_cards"
        ) as generate:
            with patch(
                "study.services._gemini_urllib_adapter"
            ) as provider:
                response = self.client.post(
                    self.home_url,
                    data=self.post_data("Қысқа мәтін."),
                )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].is_bound)
        self.assertFalse(response.context["form"].is_valid())

        generate.assert_not_called()
        provider.assert_not_called()
        self.assert_database_empty()

    def test_invalid_quote_rejects_entire_result(self):
        invalid_cards = deepcopy(DEMO_CARDS)
        invalid_cards[1]["source_quote"] = (
            "Бұл дәйексөз бастапқы мәтінде жоқ."
        )

        with self.assertRaises(GenerationError):
            validate_cards(
                {"cards": invalid_cards},
                DEMO_TEXT,
            )

        with patch(
            "study.views.generate_cards",
            return_value=invalid_cards,
        ) as generate:
            with patch(
                "study.services._gemini_urllib_adapter"
            ) as provider:
                response = self.client.post(
                    self.home_url,
                    data=self.post_data(),
                )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].is_bound)
        self.assertTrue(
            response.context["form"].non_field_errors()
        )

        generate.assert_called_once_with(DEMO_TEXT)
        provider.assert_not_called()
        self.assert_database_empty()

    def test_provider_generation_error_preserves_bound_form(self):
        with patch(
            "study.views.generate_cards",
            side_effect=GenerationError(
                "AI сервисімен байланысу мүмкін болмады."
            ),
        ) as generate:
            with patch(
                "study.services._gemini_urllib_adapter"
            ) as provider:
                response = self.client.post(
                    self.home_url,
                    data=self.post_data(),
                )

        self.assertEqual(response.status_code, 200)

        form = response.context["form"]

        self.assertTrue(form.is_bound)
        self.assertEqual(form["title"].value(), self.title)
        self.assertEqual(form["text"].value(), DEMO_TEXT)
        self.assertTrue(form.non_field_errors())

        generate.assert_called_once_with(DEMO_TEXT)
        provider.assert_not_called()
        self.assert_database_empty()

    def test_database_error_on_second_card_rolls_back_all(self):
        original_create = Flashcard.objects.create
        successful_first_write = []

        def fail_on_second_card(*args, **kwargs):
            if kwargs["position"] == 2:
                self.assertEqual(
                    Flashcard.objects.count(),
                    1,
                )
                self.assertEqual(
                    Source.objects.count(),
                    1,
                )
                raise DatabaseError(
                    "Simulated database write failure"
                )

            result = original_create(*args, **kwargs)

            if kwargs["position"] == 1:
                successful_first_write.append(result.pk)

            return result

        with patch(
            "study.models.Flashcard.objects.create",
            side_effect=fail_on_second_card,
        ):
            with patch(
                "study.services._gemini_urllib_adapter"
            ) as provider:
                response = self.client.post(
                    self.home_url,
                    data=self.post_data(),
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(successful_first_write), 1)

        form = response.context["form"]

        self.assertTrue(form.is_bound)
        self.assertEqual(form["title"].value(), self.title)
        self.assertEqual(form["text"].value(), DEMO_TEXT)
        self.assertTrue(form.non_field_errors())

        provider.assert_not_called()

        # Бірінші карточка шын жазылған,
        # бірақ екінші карточкадағы қате
        # бүкіл транзакцияны кері қайтаруы тиіс.
        self.assert_database_empty()

    def test_two_detail_gets_do_not_call_provider_or_write_db(self):
        source = Source.objects.create(
            title=self.title,
            text=DEMO_TEXT,
            generation_mode="demo",
        )

        for position, card in enumerate(DEMO_CARDS, start=1):
            Flashcard.objects.create(
                source=source,
                position=position,
                question=card["question"],
                answer=card["answer"],
                source_quote=card["source_quote"],
            )

        detail_url = reverse(
            "source_detail",
            kwargs={"pk": source.pk},
        )

        initial_source_count = Source.objects.count()
        initial_card_count = Flashcard.objects.count()

        with patch(
            "study.views.generate_cards"
        ) as generate:
            with patch(
                "study.services._gemini_urllib_adapter"
            ) as provider:
                first_response = self.client.get(detail_url)
                second_response = self.client.get(detail_url)

        generate.assert_not_called()
        provider.assert_not_called()

        for response in (first_response, second_response):
            self.assertEqual(response.status_code, 200)
            self.assertTemplateUsed(
                response,
                "study/source_detail.html",
            )

            self.assertEqual(
                response.context["source"].pk,
                source.pk,
            )

            self.assertEqual(
                [
                    card.position
                    for card in response.context["cards"]
                ],
                [1, 2, 3],
            )

            self.assertContains(
                response,
                DEMO_CARDS[0]["question"],
            )
            self.assertContains(
                response,
                DEMO_CARDS[0]["answer"],
            )
            self.assertContains(
                response,
                DEMO_CARDS[0]["source_quote"],
            )
            self.assertContains(
                response,
                "<details>",
                html=False,
            )
            self.assertContains(
                response,
                "<summary>",
                html=False,
            )

        self.assertEqual(
            Source.objects.count(),
            initial_source_count,
        )
        self.assertEqual(
            Flashcard.objects.count(),
            initial_card_count,
        )
