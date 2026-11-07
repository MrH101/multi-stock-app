from dashboard.cart import Cart
#from dashboard.expiry_date import ExpiryDate
from notifications_app.models import BroadcastNotification

## broadcast notifications
def notifications(request):
    allnotifications = BroadcastNotification.objects.all()
    return {'notifications': allnotifications}

# items in cart notification
def cart(request):
    return {'cart': Cart(request)}

# products about to expire notification
# def expiry_date(request):
#    return {'expiry_date': ExpiryDate()}