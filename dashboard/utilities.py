from .cart import Cart

from django.conf import settings
# for HTML Email
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from .models import Budget, Message, Order, OrderItem, RepliedMessage

#chanaging last_name and first_name to contact_person and pharmacy_name
def checkout(request, user, pharmacy_name, contact_person, email, phone,  address, amount):
    order = Order.objects.create(user=user, pharmacy_name = pharmacy_name, contact_person=contact_person, email=email, phone=phone, address=address, paid_amount=amount)

    for item in Cart(request):
        OrderItem.objects.create(order=order, product=item['product'], vendor=item['product'].vendor, price=item['product'].price, quantity=item['quantity'])
        order.vendors.add(item['product'].vendor)
        
    return order

def notify_vendor(order):
    from_email = settings.DEFAULT_EMAIL_FROM

    for vendor in order.vendors.all():
        to_email = vendor.email
        subject = 'New order'
        text_content = 'You have a new order!'
        html_content = render_to_string('skeleton/email_notify_vendor.html', {'order': order, 'vendor': vendor})

        msg = EmailMultiAlternatives(subject, text_content, from_email, [to_email])
        msg.attach_alternative(html_content, 'text/html')
        msg.send()

def notify_customer(order):
    from_email = settings.DEFAULT_EMAIL_FROM

    to_email = order.email
    subject = 'Order confirmation'
    text_content = 'Thank you for the order!'
    html_content = render_to_string('skeleton/email_notify_customer.html', {'order': order})

    msg = EmailMultiAlternatives(subject, text_content, from_email, [to_email])
    msg.attach_alternative(html_content, 'text/html')
    msg.send()
    
    
    
    
def saved_message(user, email_to, phone_number, message):
    saved_msg = Message.objects.create(user=user, email_to=email_to, phone_number=phone_number,message=message)
    return saved_msg


def replied_message(user, email, subject, message):
    replied_msg = RepliedMessage.objects.create(user=user, email=email, subject=subject,message=message)  
    return replied_msg

def budget_saved(user, currency, amount):
    bgt = Budget.objects.create(user=user, currency=currency, amount=amount)  
    return bgt