from django.conf import settings
from django.db import DatabaseError, transaction
from django.db.models import Count, Q
from django.http import HttpResponseBadRequest
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods, require_POST

from .demo import DEMO_TITLE, DEMO_TEXT
from .forms import FlashcardForm, SourceForm
from .models import Source, Flashcard
from .services import (
    GenerationError,
    generate_cards,
    validate_cards,
)


DATABASE_ERROR_MESSAGE = (
    "Деректерді сақтау кезінде қате пайда болды. "
    "Кейінірек қайта көріңіз."
)


def get_generation_mode():
    mode = getattr(settings, "TEACHME_MODE", "demo")

    if not isinstance(mode, str):
        raise GenerationError(
            "Генерация режимі дұрыс орнатылмаған."
        )

    mode = mode.strip().lower()

    if mode not in ("demo", "live"):
        raise GenerationError(
            "Генерация режимі дұрыс орнатылмаған."
        )

    return mode


def home(request):
    saved_sources = Source.objects.all()
    mode = getattr(settings, "TEACHME_MODE", "demo")

    if isinstance(mode, str):
        mode = mode.strip().lower()
    else:
        mode = "unknown"

    if request.method == "POST":
        form = SourceForm(request.POST)

        if form.is_valid():
            title = form.cleaned_data["title"]
            text = form.cleaned_data["text"]

            try:
                generation_mode = get_generation_mode()

                # Генерация транзакциядан бұрын аяқталады.
                cards = generate_cards(text)

                # Қосымша толық валидация.
                cards = validate_cards(
                    {"cards": cards},
                    text,
                )

            except GenerationError as exc:
                form.add_error(None, str(exc))

            else:
                try:
                    # Source және барлық Flashcard
                    # бір транзакцияда сақталады.
                    with transaction.atomic():
                        source = Source.objects.create(
                            title=title,
                            text=text,
                            generation_mode=generation_mode,
                        )

                        for position, card in enumerate(
                            cards,
                            start=1,
                        ):
                            Flashcard.objects.create(
                                source=source,
                                position=position,
                                question=card["question"],
                                answer=card["answer"],
                                source_quote=card["source_quote"],
                            )

                except DatabaseError:
                    # atomic блогынан тыс өңделеді.
                    # Транзакция толық rollback жасайды.
                    form.add_error(
                        None,
                        DATABASE_ERROR_MESSAGE,
                    )

                else:
                    return redirect(
                        "source_detail",
                        pk=source.pk,
                    )

    else:
        form = SourceForm(
            initial={
                "title": DEMO_TITLE,
                "text": DEMO_TEXT,
            }
        )

    return render(
        request,
        "study/home.html",
        {
            "form": form,
            "mode": mode,
            "saved_sources": saved_sources,
        },
    )


def source_detail(request, pk):
    source = get_object_or_404(Source, pk=pk)
    status = request.GET.get("status", "all")

    if status not in ("all", "pending", "verified"):
        status = "all"

    source_cards = source.cards.all()
    counts = source_cards.aggregate(
        total_count=Count("pk"),
        verified_count=Count("pk", filter=Q(is_verified=True)),
    )
    total_count = counts["total_count"]
    verified_count = counts["verified_count"]
    pending_count = total_count - verified_count

    cards = source_cards.order_by("position", "pk")
    if status != "all":
        cards = cards.filter(is_verified=(status == "verified"))

    return render(
        request,
        "study/source_detail.html",
        {
            "source": source,
            "cards": list(cards),
            "status": status,
            "total_count": total_count,
            "verified_count": verified_count,
            "pending_count": pending_count,
        },
    )


def card_edit(request, pk):
    card = get_object_or_404(Flashcard.objects.select_related("source"), pk=pk)

    if request.method == "POST":
        form = FlashcardForm(request.POST, instance=card)

        if form.is_valid():
            card = form.save(commit=False)
            card.is_verified = False
            card.save(
                update_fields=("question", "answer", "source_quote", "is_verified"),
            )
            return redirect("source_detail", pk=card.source_id)
    else:
        form = FlashcardForm(instance=card)

    return render(
        request,
        "study/card_form.html",
        {
            "card": card,
            "source": card.source,
            "form": form,
        },
    )


@require_http_methods(["GET", "POST"])
def card_delete(request, pk):
    card = get_object_or_404(Flashcard, pk=pk)

    if request.method == "POST":
        source_id = card.source_id
        card.delete()
        return redirect("source_detail", pk=source_id)

    return render(
        request,
        "study/card_confirm_delete.html",
        {"card": card},
    )


@require_POST
@csrf_protect
def card_review(request, pk):
    card = get_object_or_404(Flashcard, pk=pk)
    action = request.POST.get("action")

    if action not in ("verify", "reset"):
        return HttpResponseBadRequest("Карточканы тексеру әрекеті жарамсыз.")

    card.is_verified = action == "verify"
    card.save(update_fields=("is_verified",))

    return redirect("source_detail", pk=card.source_id)