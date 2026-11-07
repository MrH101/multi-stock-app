from notifications_app.models import BroadcastNotification
from django import forms


class BroadcastForm(forms.ModelForm):
    class Meta:
        model = BroadcastNotification
        fields = [
            'message',
            'broadcast_on',
        ]