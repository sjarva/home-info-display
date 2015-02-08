from django.db import models
from django.utils.timezone import now
import datetime
from django.db.models.signals import pre_delete
from django.db.models.signals import post_save

from django.dispatch import receiver
import redis
r = redis.StrictRedis()

class Task(models.Model):
    title = models.TextField()
    optional = models.NullBooleanField(default=False, null=True)
    snooze = models.DateTimeField(null=True)
    repeat_every_n_seconds = models.IntegerField()
    last_completed_at = models.DateTimeField(null=True, blank=True)

    def time_since_completion(self):
        if self.last_completed_at is None:
            return None
        return now() - self.last_completed_at

    def overdue_by(self):
        if self.snooze:
            if self.snooze < now():
                self.snooze = None
                self.save()
            else:
                return now() - self.snooze
        tsc = self.time_since_completion()
        if tsc is None:
            return datetime.timedelta(0)
        return self.time_since_completion() - datetime.timedelta(seconds=self.repeat_every_n_seconds)

    def snooze_by(self, days):
        if not self.snooze:
            self.snooze = now()
        self.snooze += datetime.timedelta(days=days)
        self.save()

    def completed(self):
        n = now()
        self.last_completed_at = n
        self.snooze = 0
        a = TaskHistory(task=self, completed_at=n)
        a.save()
        self.save()

    def undo_completed(self):
        try:
            latest = TaskHistory.objects.filter(task=self).latest()
            latest.delete()
            latest = TaskHistory.objects.filter(task=self).latest()
            self.last_completed_at = latest.completed_at
            self.save()
            return True
        except TaskHistory.DoesNotExist:
            return False

    def __unicode__(self):
        return u"%s (%sd)" % (self.title, (self.repeat_every_n_seconds / 86400))

class TaskHistory(models.Model):
    class Meta:
        get_latest_by = "completed_at"

    task = models.ForeignKey("Task")
    completed_at = models.DateTimeField(null=True)

@receiver(pre_delete, sender=Task, dispatch_uid='task_delete_signal')
def publish_task_deleted(sender, instance, using, **kwargs):
    r.publish("home:broadcast:repeating_tasks", "updated")

@receiver(post_save, sender=Task, dispatch_uid="task_saved_signal")
def publish_task_saved(sender, instance, *args, **kwargs):
    r.publish("home:broadcast:repeating_tasks", "updated")
