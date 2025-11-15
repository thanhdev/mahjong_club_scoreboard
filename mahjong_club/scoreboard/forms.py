# forms.py
from django import forms
from datetime import date
from .models import Transaction, Player


class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = ["player", "transaction_type", "weekday", "value", "description"]
        widgets = {
            "player": forms.Select(attrs={"class": "form-control"}),
            "transaction_type": forms.Select(attrs={"class": "form-control"}),
            "weekday": forms.Select(attrs={"class": "form-control"}),
            "value": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["player"].queryset = Player.objects.filter(
            name__isnull=False
        ).order_by("name")
        self.fields["player"].required = True
        # Limit transaction types for user input
        self.fields["transaction_type"].choices = [
            ("SESSION", "Session Score"),
            ("PAYIN", "Pay-in"),
            ("PAYOUT", "Pay-out"),
        ]
        self.fields["weekday"].required = False
        self.fields["weekday"].initial = Transaction.WEEKDAYS[date.today().weekday()][0]
        self.fields["description"].required = False


class PlayerForm(forms.ModelForm):
    class Meta:
        model = Player
        fields = ["name"]
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Enter player name"}
            ),
        }
