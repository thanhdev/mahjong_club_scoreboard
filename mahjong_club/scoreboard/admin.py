# admin.py
from django.contrib import admin
from .models import Player, Week, Transaction, Pool


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ["name", "total_score", "created_at"]
    search_fields = ["name"]
    readonly_fields = ["created_at"]


@admin.register(Week)
class WeekAdmin(admin.ModelAdmin):
    list_display = ["week_number", "year", "start_date", "end_date", "is_current"]
    list_filter = ["year", "is_current"]
    readonly_fields = ["created_at"]


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "player",
        "transaction_type",
        "weekday",
        "value",
        "week",
        "is_reverted",
        "created_at",
    ]
    list_filter = ["transaction_type", "weekday", "is_reverted", "week"]
    search_fields = ["player__name", "description"]
    readonly_fields = ["created_at"]
    date_hierarchy = "created_at"


@admin.register(Pool)
class PoolAdmin(admin.ModelAdmin):
    list_display = ["balance", "updated_at"]
    readonly_fields = ["updated_at"]
