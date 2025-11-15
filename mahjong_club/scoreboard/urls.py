from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("add-transaction/", views.add_transaction, name="add_transaction"),
    path("transaction-history/", views.transaction_history, name="transaction_history"),
    path(
        "revert-transaction/<int:transaction_id>/",
        views.revert_transaction,
        name="revert_transaction",
    ),
    path("new-week/", views.new_week, name="new_week"),
    path("manage-players/", views.manage_players, name="manage_players"),
    path("week-history/", views.week_history, name="week_history"),
]
