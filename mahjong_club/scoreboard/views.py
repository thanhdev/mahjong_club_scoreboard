# views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import Player, Week, Transaction, Pool
from .forms import TransactionForm, PlayerForm


def dashboard(request):
    """Main dashboard view showing all players and their scores"""
    current_week = Week.get_current_week()
    players = Player.objects.all()
    pool = Pool.get_pool()

    # Prepare player data
    player_data = []
    weekdays = ['Monday', 'Tuesday', 'Wednesday',
                'Thursday', 'Friday', 'Saturday', 'Sunday']

    for player in players:
        session_scores = player.get_session_scores()
        player_info = {
            'player': player,
            'total_score': player.total_score,
            'payin_payout': player.get_payin_payout_balance(),
            'weekly_total': player.get_weekly_total(),
            'sessions': [session_scores.get(day, 0) for day in weekdays]
        }
        player_data.append(player_info)

    context = {
        'player_data': player_data,
        'weekdays': weekdays,
        'current_week': current_week,
        'pool': pool,
    }
    return render(request, 'mahjong/dashboard.html', context)


def add_transaction(request):
    """Add a new transaction (score input)"""
    if request.method == 'POST':
        form = TransactionForm(request.POST)
        if form.is_valid():
            transaction = form.save(commit=False)
            transaction.week = Week.get_current_week()

            # Validate SESSION type must have weekday
            if transaction.transaction_type == 'SESSION' and not transaction.weekday:
                messages.error(
                    request, 'Session transactions must specify a weekday.')
                return render(request, 'mahjong/add_transaction.html', {'form': form})

            transaction.save()
            messages.success(request, 'Transaction added successfully!')
            return redirect('dashboard')
    else:
        form = TransactionForm()

    return render(request, 'mahjong/add_transaction.html', {'form': form})


def transaction_history(request):
    """View transaction history with revert capability"""
    current_week = Week.get_current_week()
    transactions = Transaction.objects.filter(
        week=current_week,
        is_reverted=False
    ).select_related('player', 'week')

    context = {
        'transactions': transactions,
        'current_week': current_week,
    }
    return render(request, 'mahjong/transaction_history.html', context)


def revert_transaction(request, transaction_id):
    """Revert a specific transaction"""
    transaction = get_object_or_404(Transaction, id=transaction_id)

    if not transaction.is_reverted:
        transaction.revert()
        messages.success(
            request, f'Transaction #{transaction_id} has been reverted.')
    else:
        messages.warning(
            request, 'This transaction has already been reverted.')

    return redirect('transaction_history')


def new_week(request):
    """Process 'New Week' button - finalize current week and start new one"""
    if request.method == 'POST':
        try:
            new_week = Week.start_new_week()
            messages.success(
                request, f'New week started: {new_week}. Previous week has been finalized with cashback applied.')
            return redirect('dashboard')
        except Exception as e:
            messages.error(request, f'Error starting new week: {str(e)}')
            return redirect('dashboard')

    # Show confirmation page
    current_week = Week.get_current_week()
    players = Player.objects.all()

    # Preview what will happen
    preview_data = []
    for player in players:
        weekly_total = player.get_weekly_total()
        preview_data.append({
            'player': player,
            'weekly_total': weekly_total,
            'new_total': player.total_score + weekly_total
        })

    context = {
        'current_week': current_week,
        'preview_data': preview_data,
    }
    return render(request, 'mahjong/new_week_confirm.html', context)


def manage_players(request):
    """Manage players - add/view players"""
    if request.method == 'POST':
        form = PlayerForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Player added successfully!')
            return redirect('manage_players')
    else:
        form = PlayerForm()

    players = Player.objects.all()
    context = {
        'form': form,
        'players': players,
    }
    return render(request, 'mahjong/manage_players.html', context)


def week_history(request):
    """View history of all weeks"""
    weeks = Week.objects.all()
    context = {
        'weeks': weeks,
    }
    return render(request, 'mahjong/week_history.html', context)
