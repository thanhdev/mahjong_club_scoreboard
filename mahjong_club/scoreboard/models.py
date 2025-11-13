# models.py
from django.db import models
from django.db.models import Sum
from django.utils import timezone
from decimal import Decimal


class Player(models.Model):
    name = models.CharField(max_length=100, unique=True)
    total_score = models.DecimalField(
        max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def get_payin_payout_balance(self):
        """Calculate total pay-in/pay-out balance for current week"""
        balance = Transaction.objects.filter(
            player=self,
            week=Week.get_current_week(),
            transaction_type__in=['PAYIN', 'PAYOUT']
        ).aggregate(total=Sum('value'))['total'] or Decimal('0')
        return balance

    def get_weekly_total(self):
        """Calculate total for the current week including sessions and pay-in/out"""
        current_week = Week.get_current_week()
        total = Transaction.objects.filter(
            player=self,
            week=current_week
        ).aggregate(total=Sum('value'))['total'] or Decimal('0')
        return total

    def get_session_scores(self):
        """Get session scores for each weekday"""
        current_week = Week.get_current_week()
        weekdays = ['Monday', 'Tuesday', 'Wednesday',
                    'Thursday', 'Friday', 'Saturday', 'Sunday']
        scores = {}
        for day in weekdays:
            score = Transaction.objects.filter(
                player=self,
                week=current_week,
                transaction_type='SESSION',
                weekday=day
            ).aggregate(total=Sum('value'))['total'] or Decimal('0')
            scores[day] = score
        return scores


class Week(models.Model):
    week_number = models.IntegerField()
    year = models.IntegerField()
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_current = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-year', '-week_number']
        unique_together = ['week_number', 'year']

    def __str__(self):
        return f"Week {self.week_number}, {self.year}"

    @classmethod
    def get_current_week(cls):
        """Get or create the current week"""
        current_week = cls.objects.filter(is_current=True).first()
        if not current_week:
            # Create first week
            today = timezone.now().date()
            current_week = cls.objects.create(
                week_number=1,
                year=today.year,
                start_date=today,
                is_current=True
            )
        return current_week

    @classmethod
    def start_new_week(cls):
        """Process 'New Week' - finalize current week and start a new one"""
        current_week = cls.get_current_week()
        current_week.is_current = False
        current_week.end_date = timezone.now().date()
        current_week.save()

        # Update all players' total scores
        for player in Player.objects.all():
            weekly_total = player.get_weekly_total()
            player.total_score += weekly_total
            player.save()

        # Apply cashback
        cls.apply_cashback(current_week)

        # Create new week
        new_week = cls.objects.create(
            week_number=current_week.week_number + 1,
            year=current_week.year,
            start_date=timezone.now().date(),
            is_current=True
        )
        return new_week

    @classmethod
    def apply_cashback(cls, week):
        """Calculate and apply cashback for the completed week"""
        pool = Pool.get_pool()
        cashback_total = Decimal('0')

        # Find players with losses and calculate cashback
        for player in Player.objects.all():
            weekly_total = Transaction.objects.filter(
                player=player,
                week=week
            ).aggregate(total=Sum('value'))['total'] or Decimal('0')

            cashback = Decimal('0')
            if weekly_total <= -200 and weekly_total > -500:
                cashback = Decimal('50')
            elif weekly_total <= -500:
                cashback = Decimal('100')

            if cashback > 0:
                # Create cashback transaction
                Transaction.objects.create(
                    player=player,
                    week=week,
                    transaction_type='CASHBACK',
                    value=cashback,
                    description=f"Cashback for losses of {weekly_total}"
                )
                cashback_total += cashback

        if cashback_total > 0:
            # Find winning players
            winners = []
            for player in Player.objects.all():
                weekly_total = Transaction.objects.filter(
                    player=player,
                    week=week
                ).aggregate(total=Sum('value'))['total'] or Decimal('0')
                if weekly_total > 0:
                    winners.append((player, weekly_total))

            if winners:
                # Sort by winning amount (highest first)
                winners.sort(key=lambda x: x[1], reverse=True)

                # Distribute cashback deductions
                per_winner = (cashback_total / len(winners)
                              ).quantize(Decimal('0.01'))
                distributed = Decimal('0')

                for i, (player, _) in enumerate(winners):
                    if i == len(winners) - 1:
                        # Last winner gets the remainder
                        deduction = cashback_total - distributed
                    else:
                        deduction = per_winner

                    Transaction.objects.create(
                        player=player,
                        week=week,
                        transaction_type='CASHBACK_DEDUCTION',
                        value=-deduction,
                        description="Cashback deduction"
                    )
                    distributed += deduction

                # Any rounding remainder goes to pool
                remainder = cashback_total - distributed
                if remainder > 0:
                    pool.balance += remainder
                    pool.save()
                    Transaction.objects.create(
                        week=week,
                        transaction_type='POOL_ADDITION',
                        value=remainder,
                        description="Cashback distribution remainder"
                    )


class Transaction(models.Model):
    TRANSACTION_TYPES = [
        ('PAYIN', 'Pay-in'),
        ('PAYOUT', 'Pay-out'),
        ('SESSION', 'Session Score'),
        ('CASHBACK', 'Cashback'),
        ('CASHBACK_DEDUCTION', 'Cashback Deduction'),
        ('POOL_ADDITION', 'Pool Addition'),
    ]

    WEEKDAYS = [
        ('Monday', 'Monday'),
        ('Tuesday', 'Tuesday'),
        ('Wednesday', 'Wednesday'),
        ('Thursday', 'Thursday'),
        ('Friday', 'Friday'),
        ('Saturday', 'Saturday'),
        ('Sunday', 'Sunday'),
    ]

    player = models.ForeignKey(
        Player, on_delete=models.CASCADE, null=True, blank=True)
    week = models.ForeignKey(Week, on_delete=models.CASCADE)
    transaction_type = models.CharField(
        max_length=20, choices=TRANSACTION_TYPES)
    weekday = models.CharField(
        max_length=10, choices=WEEKDAYS, null=True, blank=True)
    value = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_reverted = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        player_name = self.player.name if self.player else "Pool"
        return f"{player_name} - {self.get_transaction_type_display()} - {self.value}"

    def revert(self):
        """Revert this transaction"""
        if not self.is_reverted:
            # Create a reversing transaction
            Transaction.objects.create(
                player=self.player,
                week=self.week,
                transaction_type=self.transaction_type,
                weekday=self.weekday,
                value=-self.value,
                description=f"Reversal of transaction #{self.id}"
            )
            self.is_reverted = True
            self.save()


class Pool(models.Model):
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def get_pool(cls):
        """Get or create the pool singleton"""
        pool, created = cls.objects.get_or_create(id=1)
        return pool

    def __str__(self):
        return f"Pool: {self.balance}"
