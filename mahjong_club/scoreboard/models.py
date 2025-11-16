# models.py
from django.db import models
from django.db.models import Sum
from django.utils import timezone
from decimal import Decimal


class Player(models.Model):
    name = models.CharField(max_length=100, unique=True)
    total_score = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_payin_payout_balance(self):
        """Calculate total pay-in/pay-out balance for current week"""
        balance = Transaction.objects.filter(
            player=self,
            transaction_type=Transaction.TransactionType.PAYIN_OUT,
        ).aggregate(total=Sum("value"))["total"] or Decimal("0")
        return balance

    def get_weekly_total(self):
        """Calculate total for the current week including sessions and pay-in/out"""
        current_week = Week.get_current_week()
        total = Transaction.objects.filter(
            player=self,
            week=current_week,
            transaction_type=Transaction.TransactionType.SESSION,
        ).aggregate(total=Sum("value"))["total"] or Decimal("0")
        return total

    def get_session_scores(self):
        """Get session scores for each weekday"""
        current_week = Week.get_current_week()
        weekdays = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        scores = {}
        for day in weekdays:
            score = Transaction.objects.filter(
                player=self, week=current_week, transaction_type="SESSION", weekday=day
            ).aggregate(total=Sum("value"))["total"] or Decimal("0")
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
        ordering = ["-year", "-week_number"]
        unique_together = ["week_number", "year"]

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
                week_number=1, year=today.year, start_date=today, is_current=True
            )
        return current_week

    @classmethod
    def start_new_week(cls):
        """Process 'New Week' - finalize current week and start a new one"""
        current_week = cls.get_current_week()
        pool = Pool.get_pool()
        cashback_total = Decimal("0")

        # Validate that for each weekday, the sum of SESSION transactions across all players is zero
        weekdays = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        imbalanced = []
        for day in weekdays:
            total_for_day = (
                Transaction.objects.filter(week=current_week, transaction_type="SESSION", weekday=day)
                .aggregate(total=Sum("value"))["total"]
                or Decimal("0")
            )
            if total_for_day != Decimal("0"):
                imbalanced.append((day, total_for_day))
        if imbalanced:
            # Build a helpful error message
            msg_parts = [f"{d}: {t}" for d, t in imbalanced]
            raise ValueError(
                "Session totals are not balanced for the following weekdays: " + ", ".join(msg_parts)
            )

        # Update all players' total scores and also apply cashback
        for player in Player.objects.all():
            weekly_total = player.get_weekly_total()
            player.total_score += weekly_total
            if weekly_total >= 500:
                player.total_score -= Decimal("100")
                cashback_total += Decimal("100")
            elif weekly_total >= 200:
                player.total_score -= Decimal("50")
                cashback_total += Decimal("50")
            elif weekly_total <= -200 and weekly_total > -500:
                player.total_score += Decimal("50")
                cashback_total -= Decimal("50")
            elif weekly_total <= -500:
                player.total_score += Decimal("100")
                cashback_total -= Decimal("100")
            else:
                pass
            player.save()
        # Update pool balance
        if cashback_total != 0:
            pool.balance += cashback_total
            pool.save()
            Transaction.objects.create(
                week=current_week,
                transaction_type=Transaction.TransactionType.POOL_ADDITION,
                value=cashback_total,
                description="Cashback to pool",
            )

        # Finalize current week
        current_week.is_current = False
        current_week.end_date = timezone.now().date()
        current_week.save()

        # Create new week
        new_week = cls.objects.create(
            week_number=current_week.week_number + 1,
            year=current_week.year,
            start_date=timezone.now().date(),
            is_current=True,
        )
        return new_week


class Transaction(models.Model):
    class TransactionType(models.TextChoices):
        PAYIN_OUT = "PAYIN/OUT", "Pay-in/Out"
        SESSION = "SESSION", "Session Score"
        CASHBACK = "CASHBACK", "Cashback"
        CASHBACK_DEDUCTION = "CASHBACK_DEDUCTION", "Cashback Deduction"
        POOL_ADDITION = "POOL_ADDITION", "Pool Addition"

    class Weekday(models.TextChoices):
        MONDAY = "Monday", "Monday"
        TUESDAY = "Tuesday", "Tuesday"
        WEDNESDAY = "Wednesday", "Wednesday"
        THURSDAY = "Thursday", "Thursday"
        FRIDAY = "Friday", "Friday"
        SATURDAY = "Saturday", "Saturday"
        SUNDAY = "Sunday", "Sunday"

    player = models.ForeignKey(Player, on_delete=models.CASCADE, null=True, blank=True)
    week = models.ForeignKey(Week, on_delete=models.CASCADE)
    transaction_type = models.CharField(max_length=20, choices=TransactionType.choices)
    weekday = models.CharField(max_length=10, choices=Weekday.choices, null=True, blank=True)
    value = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_reverted = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

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
                description=f"Reversal of transaction #{self.id}",
            )
            # Adjust player's total_score for PAYIN/OUT reversals
            if self.player and self.transaction_type == "PAYIN/OUT":
                self.player.total_score -= self.value
                self.player.save()

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
