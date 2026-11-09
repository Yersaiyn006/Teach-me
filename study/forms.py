from django import forms

from .models import Flashcard


class SourceForm(forms.Form):
    title = forms.CharField(
        label="Тақырып",
        required=True,
        max_length=120,
        strip=True,
    )

    text = forms.CharField(
        label="Оқу мәтіні",
        required=True,
        min_length=80,
        max_length=12000,
        strip=True,
        widget=forms.Textarea(
            attrs={
                "rows": 12,
            }
        ),
    )

    def clean_text(self):
        text = self.cleaned_data["text"]
        return text.replace("\r\n", "\n").replace("\r", "\n")


class FlashcardForm(forms.ModelForm):
    class Meta:
        model = Flashcard
        fields = ("question", "answer", "source_quote")
        labels = {
            "question": "Сұрақ",
            "answer": "Жауап",
            "source_quote": "Бастапқы мәтіннен дәйексөз",
        }

    def clean_source_quote(self):
        quote = self.cleaned_data["source_quote"]
        quote = quote.replace("\r\n", "\n").replace("\r", "\n")

        if quote not in self.instance.source.text:
            raise forms.ValidationError(
                "Дәйексөз бастапқы мәтінде дәл осы қалпында болуы керек."
            )

        return quote