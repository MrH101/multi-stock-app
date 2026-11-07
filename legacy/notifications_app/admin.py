from django.contrib import admin
from .models import BroadcastNotification
# Register your models here.

class AdminBroadcast(admin.ModelAdmin):
    list_display =('message', 'broadcast_on')

admin.site.register(BroadcastNotification, AdminBroadcast)