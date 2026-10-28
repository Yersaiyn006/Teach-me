
from django import forms


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
