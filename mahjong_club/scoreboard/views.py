# views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Sum
from .models import Player, Week, Transaction, Pool
from .forms import TransactionForm, PlayerForm
from django.template.loader import render_to_string
from django.http import HttpResponse, HttpResponseBadRequest
from decimal import Decimal


def dashboard(request):
    """Main dashboard view showing all players and their scores"""
    current_week = Week.get_current_week()
    players = Player.objects.all()
    pool = Pool.get_pool()

    # Prepare player data
    player_data = []
    weekdays = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]

    for player in players:
        session_scores = player.get_session_scores()
        # build list of (weekday, score) pairs to allow weekday-aware rendering in template
        session_list = [(day, session_scores.get(day, 0)) for day in weekdays]
        player_info = {
            "player": player,
            "total_score": player.total_score,
            "payin_payout": player.get_payin_payout_balance(),
            "weekly_total": player.get_weekly_total(),
            "sessions": session_list,
        }
        player_data.append(player_info)

    context = {
        "player_data": player_data,
        "weekdays": weekdays,
        "current_week": current_week,
        "pool": pool,
    }
    return render(request, "mahjong/dashboard.html", context)


def add_transaction(request):
    """Add a new transaction (score input)"""
    if request.method == "POST":
        form = TransactionForm(request.POST)
        if form.is_valid():
            transaction = form.save(commit=False)
            transaction.week = Week.get_current_week()

            # Validate SESSION type must have weekday
            if transaction.transaction_type == "SESSION" and not transaction.weekday:
                messages.error(request, "Session transactions must specify a weekday.")
                return render(request, "mahjong/add_transaction.html", {"form": form})

            # If PAYIN/OUT, update player's total_score
            if transaction.transaction_type == "PAYIN/OUT" and transaction.player:
                transaction.player.total_score += transaction.value
                transaction.player.save()

            transaction.save()
            messages.success(request, "Transaction added successfully!")
            return redirect("dashboard")
    else:
        form = TransactionForm()

    return render(request, "mahjong/add_transaction.html", {"form": form})


def add_session_htmx(request):
    """HTMX endpoint to add a SESSION transaction and return updated weekday cell fragment."""
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    player_id = request.POST.get("player")
    weekday = request.POST.get("weekday")
    value = request.POST.get("value")

    if not player_id or not weekday or value in (None, ""):
        return HttpResponseBadRequest("Missing fields")

    try:
        player = Player.objects.get(id=player_id)
        value_dec = Decimal(value)
    except Exception:
        return HttpResponseBadRequest("Invalid player or value")

    transaction = Transaction.objects.create(
        player=player,
        week=Week.get_current_week(),
        transaction_type="SESSION",
        weekday=weekday,
        value=value_dec,
    )

    # Recompute the day's total across all players
    day_total = Transaction.objects.filter(
        week=Week.get_current_week(), transaction_type="SESSION", weekday=weekday
    ).aggregate(total=Sum("value"))["total"] or Decimal("0")

    # Recompute player's session score for this weekday and weekly total
    session_scores = player.get_session_scores()
    player_weekly_total = player.get_weekly_total()
    new_total = player.total_score + player_weekly_total

    # Render partial cell HTML for this player and weekday
    context = {
        "player": player,
        "weekday": weekday,
        "score": session_scores.get(weekday, Decimal("0")),
        "day_total": day_total,
        "weekly_total": player_weekly_total,
        "new_total": new_total,
    }
    html = render_to_string("mahjong/partials/weekday_cell.html", context)
    return HttpResponse(html)


def add_transaction_htmx(request):
    """HTMX endpoint to add a PAYIN or PAYOUT transaction and return updated payin cell fragment."""
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")

    player_id = request.POST.get("player")
    transaction_type = request.POST.get("transaction_type")
    value = request.POST.get("value")

    if not player_id or not transaction_type or value in (None, ""):
        return HttpResponseBadRequest("Missing fields")

    # Accept the combined PAYIN/OUT transaction type
    if transaction_type != "PAYIN/OUT":
        return HttpResponseBadRequest("Invalid transaction type")

    try:
        player = Player.objects.get(id=player_id)
        value_dec = Decimal(value)
    except Exception:
        return HttpResponseBadRequest("Invalid player or value")

    transaction = Transaction.objects.create(
        player=player,
        week=Week.get_current_week(),
        transaction_type=transaction_type,
        value=value_dec,
    )

    # Update player's total_score for PAYIN/OUT transactions
    if transaction_type == "PAYIN/OUT" and player:
        player.total_score += value_dec
        player.save()

    # Recompute the player's payin/payout balance for current week
    payin_total = Transaction.objects.filter(
        player=player, week=Week.get_current_week(), transaction_type__in=("PAYIN/OUT",)
    ).aggregate(total=Sum("value"))["total"] or Decimal("0")

    context = {
        "player": player,
        "payin": payin_total,
        "new_total": player.total_score,
    }
    html = render_to_string("mahjong/partials/payin_cell.html", context)
    return HttpResponse(html)


def transaction_history(request):
    """View transaction history with revert capability"""
    current_week = Week.get_current_week()
    transactions = Transaction.objects.filter(
        week=current_week, is_reverted=False
    ).select_related("player", "week")

    context = {
        "transactions": transactions,
        "current_week": current_week,
    }
    return render(request, "mahjong/transaction_history.html", context)


def revert_transaction(request, transaction_id):
    """Revert a specific transaction"""
    transaction = get_object_or_404(Transaction, id=transaction_id)
    current_week = Week.get_current_week()
    if transaction.week != current_week:
        messages.error(
            request, "Only transactions from the current week can be reverted."
        )
        return redirect("transaction_history")

    if not transaction.is_reverted:
        transaction.revert()
        messages.success(request, f"Transaction #{transaction_id} has been reverted.")
    else:
        messages.warning(request, "This transaction has already been reverted.")

    return redirect("transaction_history")


def new_week(request):
    """Process 'New Week' button - finalize current week and start new one"""
    if request.method == "POST":
        try:
            new_week = Week.start_new_week()
            messages.success(
                request,
                f"New week started: {new_week}. Previous week has been finalized with cashback applied.",
            )
            return redirect("dashboard")
        except Exception as e:
            messages.error(request, f"Error starting new week: {str(e)}")
            return redirect("dashboard")

    # Show confirmation page
    from decimal import Decimal

    current_week = Week.get_current_week()
    players = Player.objects.all()

    # Calculate original weekly totals (before cashback)
    player_totals = {}
    for player in players:
        original_total = Transaction.objects.filter(
            player=player,
            week=current_week,
            transaction_type__in=["PAYIN/OUT", "SESSION"],
        ).aggregate(total=Sum("value"))["total"] or Decimal("0")
        player_totals[player.id] = original_total

    # Calculate cashback changes using the same rules as Week.start_new_week
    # cashback_change is the amount applied to the player's total_score (negative = deduction for winners, positive = bonus for losers)
    total_cashback = Decimal(
        "0"
    )  # net amount that will be applied to the pool (positive => pool gains)
    cashback_change_map = {}
    for player in players:
        weekly_total = player_totals[player.id]
        cashback_change = Decimal("0")
        if weekly_total >= Decimal("500"):
            cashback_change = Decimal("-100")  # winner pays 100
            total_cashback += Decimal("100")
        elif weekly_total >= Decimal("200"):
            cashback_change = Decimal("-50")  # winner pays 50
            total_cashback += Decimal("50")
        elif weekly_total <= Decimal("-200") and weekly_total > Decimal("-500"):
            cashback_change = Decimal("50")  # loser receives 50
            total_cashback -= Decimal("50")
        elif weekly_total <= Decimal("-500"):
            cashback_change = Decimal("100")  # loser receives 100
            total_cashback -= Decimal("100")
        cashback_change_map[player.id] = cashback_change

    # Preview what will happen
    preview_data = []
    for player in players:
        original_weekly = player_totals[player.id]
        cashback_change = cashback_change_map.get(player.id, Decimal("0"))
        final_weekly = original_weekly + cashback_change

        preview_data.append(
            {
                "player": player,
                "weekly_total": original_weekly,
                "cashback_change": cashback_change,
                "final_weekly": final_weekly,
                "new_total": player.total_score + final_weekly,
            }
        )

    context = {
        "current_week": current_week,
        "preview_data": preview_data,
        "total_cashback": total_cashback,
    }
    return render(request, "mahjong/new_week_confirm.html", context)


def manage_players(request):
    """Manage players - add/view players"""
    if request.method == "POST":
        form = PlayerForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Player added successfully!")
            return redirect("manage_players")
    else:
        form = PlayerForm()

    players = Player.objects.all()
    context = {
        "form": form,
        "players": players,
    }
    return render(request, "mahjong/manage_players.html", context)


def week_history(request):
    """View history of all weeks"""
    weeks = Week.objects.all()
    context = {
        "weeks": weeks,
    }
    return render(request, "mahjong/week_history.html", context)
