from datetime import timedelta
from django.db import models
from django.contrib.auth.models import User
#from autoslug import AutoSlugField
from PIL import Image
from django.core.files import File
from io import BytesIO
from django.conf import settings



# Create your models here.

CATEGORY_CHOICES = (
    ('Tablets', 'Tablets'),
    ('Capsules', 'Capsules'),
    ('Suspension', 'Suspension'),
    ('Surgical', 'Surgical'),
    ('Suppository', 'Suppository'),
    ('Pessary', 'Pessary'),
    ('Ampule', 'Ampule'),
    ('Vial', 'Vial'),
    ('Pen set', 'Pen set'),
    ('Other', 'Other')
)


class Vendor(User):
    
    created_at = models.DateTimeField(auto_now_add=True)
    mcaz_license = models.CharField(null=True,blank=True,unique=True,max_length=255,help_text='MCAZ License Number')
    phone_number = models.CharField(null=True,blank=True,unique=True,max_length=255,help_text='whatsapp number')
    
    REQUIRED_FIELDS = ["mcaz_license"]

    def get_balance(self):
        items = self.items.filter(vendor_paid=False, order__vendors__in=[self.id])
        return sum((item.product.price * item.quantity) for item in items)

    def get_paid_amount(self):
        items = self.items.filter(vendor_paid=True, order__vendors__in=[self.id])
        return sum((item.product.price * item.quantity) for item in items)
    
class Customer(User):
    created_at = models.DateTimeField(auto_now_add=True,null=True,blank=True)
    
    
#admin and customer models
#Products model
class Product(models.Model):
    vendor = models.ForeignKey(Vendor, related_name="products", on_delete=models.CASCADE,null=True,blank=True)
    title = models.CharField(max_length=255,null=True, blank=True)
    slug = models.SlugField(max_length=55)
    description = models.TextField(blank=True, null=True)
    price = models.DecimalField(max_digits=50, decimal_places=2)
    added_date = models.DateTimeField(auto_now_add=True)
    category = models.CharField(choices=CATEGORY_CHOICES, max_length=255,null=True, blank=True)
    batch_number = models.CharField(max_length=255,null=True, blank=True)
    pack_size = models.CharField(max_length=255,null=True,blank=True)
    quantity = models.PositiveIntegerField(default=1)
    expiry_date = models.DateField(blank=True,null=True, help_text='date in format yyyy-mm-dd')
    
    class Meta:
        ordering = ['-added_date']

    def __str__(self):
        return self.title
    
    def get_date_before(self):
        notify_before = self.expiry_date - timedelta(days = 15)
        return notify_before
    
    
       
#Orders Model 
ORDER_STATUS = (
    ("Order Received", "Order Received"),
    ("Order Processing", "Order Processing"),
    ("On the way", "On the way"),
    ("Order Completed", "Order Completed"),
    ("Order Canceled", "Order Canceled"),
)

METHOD = (
    ("Cash On Delivery", "Cash On Delivery"),
)


class Order(models.Model):
    user = models.ForeignKey(Customer, on_delete=models.CASCADE,related_name="orders", null=True, blank=True)
    pharmacy_name =models.CharField(max_length=255,null=True,blank=True)
    contact_person = models.CharField(max_length=255,blank=True, null=True) 
    email = models.EmailField(max_length=255,null=True, blank=True)
    phone = models.CharField(max_length=255,blank=True, null=True)
    address = models.CharField(max_length=255,null=True,blank=True)
    paid_amount = models.DecimalField(null=True,blank=True,max_digits=50,decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True, null=True,blank=True)
    vendors = models.ManyToManyField(Vendor, related_name="orders", null=True, blank=True)
    payment_method = models.CharField(
        max_length=200, choices=METHOD, default="Cash On Delivery")
    order_status = models.CharField(max_length=50, choices=ORDER_STATUS, null=True,blank=True, default='Order Received')
    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.first_name

class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE,null=True,blank=True)
    product = models.ForeignKey(Product, related_name="items", on_delete=models.CASCADE,null=True,blank=True)
    vendor = models.ForeignKey(Vendor, related_name="items", on_delete=models.CASCADE)
    user = models.ForeignKey(Customer, related_name="items", on_delete=models.CASCADE,null=True,blank=True)
    vendor_paid = models.BooleanField(default=False)
    price = models.DecimalField(max_digits=50, decimal_places=2)
    quantity = models.IntegerField(default=1)

    def __str__(self):
        return str(self.id)

    def get_total_price(self):
        return self.price * self.quantity
    
class Message(models.Model):
    
    user = models.ForeignKey(Customer, on_delete=models.CASCADE, null=True, blank=True)
    email_to = models.CharField(max_length=200, blank=True,null=True)
    phone_number = models.CharField(max_length=200,blank=True,null=True)
    message = models.TextField(max_length=1000, blank=True, null=True)
    date_sent = models.DateField(auto_now_add=True)
    
    def __str__(self):
        return self.email_to
    

class RepliedMessage(models.Model):
    user = models.ForeignKey(Vendor, on_delete=models.CASCADE, null=True, blank=True)
    email = models.CharField(max_length=200, blank=True,null=True)
    subject = models.CharField(max_length=200,blank=True,null=True)
    message = models.TextField(max_length=1000, blank=True, null=True)
    date_sent = models.DateField(auto_now_add=True)
    
    def __str__(self):
        return self.email
    
    

class Budget(models.Model):
    user = models.ForeignKey(Customer, on_delete=models.CASCADE, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True,blank=True)
    currency = models.CharField(max_length=200, blank=True,null=True)
    amount = models.DecimalField(max_digits=50, decimal_places=2, default=0)
    
    def __str__(self):
        return self.currency
    

