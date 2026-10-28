
from django.conf import settings
from django.db import DatabaseError, transaction
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)

from .demo import DEMO_TITLE, DEMO_TEXT
from .forms import SourceForm
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

    cards = source.cards.order_by(
        "position",
        "id",
    )

    return render(
        request,
        "study/source_detail.html",
        {
            "source": source,
            "cards": cards,
        },
    )
