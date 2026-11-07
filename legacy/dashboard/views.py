from re import template
from urllib import request
from dashboard.cart import Cart
from asgiref.sync import async_to_sync
import json
from channels.layers import get_channel_layer
from django.shortcuts import render, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required

from dashboard.utilities import budget_saved, checkout, notify_customer, notify_vendor, replied_message, saved_message

from .models import *
from .forms import AddToCartForm, ProductForm, SupplierForm
from django.contrib import messages
from django.views.generic import DetailView, View,  TemplateView
from django.urls import reverse_lazy
from notifications_app.forms import BroadcastForm
from .forms import CreateUserForm
from django.conf import settings
from django.core.mail import send_mail
from django.utils.text import slugify

from django.template.loader import get_template
from .pdf import render_to_pdf
from datetime import datetime
from django.db.models import Sum


# Create your views here.

def login_success(request):
    if request.user.is_superuser:
        return redirect('index')
    elif request.user.is_staff:
        return redirect('index')
    elif request.user.is_authenticated:
        return redirect('index')
    elif request.user.vendor:
        return render('index')
    else:
        return redirect('index')


class GeneratePdf(View):   
    def get(self, request,*args, **kwargs):
        template = get_template('skeleton/pdf.html')
        vendor = request.user.vendor
        orders = vendor.orders.all()
        my_date = datetime.now()
        formatted_date = my_date.strftime("%Y-%m-%d %H:%M:%S")
        
        context= {
            'orders':orders,
            'my_date':formatted_date,
        }
        
        html = template.render(context)
        pdf = render_to_pdf('skeleton/pdf.html', context)
        if pdf:
            response =  HttpResponse(pdf, content_type='application/pdf')
            filename = "Invoice_%s.pdf" %("124567772")
            content = "inline; filename='%s'"%(filename)
            download = request.GET.get('download')
            if download:
                content ="attachment; filename='%s'"%(filename)  
            response['Content-Disposition'] = content        
            return response
        return HttpResponse('Error')
        
        
class GeneratePdfCustomer(View):   
    def get(self, request,*args, **kwargs):
        template = get_template('skeleton/pdf.html')
        customer = request.user.customer
        orders = customer.orders.all()
        my_date = datetime.now()
        formatted_date = my_date.strftime("%Y-%m-%d %H:%M:%S")
        
        context= {
            'orders':orders,
            'my_date':formatted_date,
        }
        
        html = template.render(context)
        pdf = render_to_pdf('skeleton/pdf_customer.html', context)
        if pdf:
            response =  HttpResponse(pdf, content_type='application/pdf')
            filename = "Invoice_%s.pdf" %("124567772")
            content = "inline; filename='%s'"%(filename)
            download = request.GET.get('download')
            if download:
                content ="attachment; filename='%s'"%(filename)  
            response['Content-Disposition'] = content        
            return response
        return HttpResponse('Error')
  
class PrintDetails(DetailView):
    def get(self, request,*args, **kwargs):
        template = get_template('skeleton/print_details.html')
        vendor = request.user.vendor
        details = Order.objects.all()
        my_date = datetime.now()
        formatted_date = my_date.strftime("%Y-%m-%d %H:%M:%S")
        
        context= {
            'details':details,
            'my_date':formatted_date,
        }
        
        html = template.render(context)
        pdf = render_to_pdf('skeleton/print_details.html', context)
        if pdf:
            response =  HttpResponse(pdf, content_type='application/pdf')
            filename = "Invoice_details_%s.pdf" %("124567772")
            content = "inline; filename='%s'"%(filename)
            download = request.GET.get('download')
            if download:
                content ="attachment; filename='%s'"%(filename)  
            response['Content-Disposition'] = content        
            return response
        return HttpResponse('Error')
    
class PrintPdfUsers(View):   
    def get(self, request,*args, **kwargs):
        template = get_template('skeleton/pdf.html')
        orders = Vendor.objects.all()
        my_date = datetime.now()
        formatted_date = my_date.strftime("%Y-%m-%d %H:%M:%S")
        
        context= {
            'orders':orders,
            'my_date':formatted_date,
        }
        
        html = template.render(context)
        pdf = render_to_pdf('skeleton/print_customers.html', context)
        if pdf:
            response =  HttpResponse(pdf, content_type='application/pdf')
            filename = "Invoice_%s.pdf" %("124567772")
            content = "inline; filename='%s'"%(filename)
            download = request.GET.get('download')
            if download:
                content ="attachment; filename='%s'"%(filename)  
            response['Content-Disposition'] = content        
            return response
        return HttpResponse('Error')
    
#from django.http import HttpResponseRedirect
def viewProduct(request, product_slug):
    # Create instance of Cart class
    cart = Cart(request)
    product = get_object_or_404(Product, slug=product_slug)
    # Check whether the AddToCart button is clicked or not
    if request.method == 'POST':

        form = AddToCartForm(request.POST)

        if form.is_valid():
            quantity = form.cleaned_data['quantity']
            if product.quantity > 0 and product.quantity > quantity: 
                cart.add(product_id=product.id, quantity=quantity, update_quantity=True)
                product.quantity = product.quantity - quantity
                product.save()
                messages.success(request, "The product was added to the cart.")
                return HttpResponse('<script>history.go(-2);</script>')    

            else:
                messages.warning(request, 'You cannot order more products than stocked.')
    else:
        form = AddToCartForm()
       
       # return quantity

    context = {
        'product': product,
        
        'form': form,
    }
    return render(request, 'skeleton/view_product.html', context)


def viewVendorProducts(request, key):
    vendor = get_object_or_404(Vendor, pk=key)
    if request.method == 'POST':
        send = Message()
        send.user = request.user.customer
        send.email_to = request.POST.get('email_to')
        send.phone_number = request.POST.get('phone_number')
        send.message = request.POST.get('message') 
        saved_message(send.user, send.email_to, send.phone_number, send.message)
        return redirect('index')
       
    context= {
        'vendor': vendor,
      
    }
    return render(request, 'skeleton/supplier_products.html', context)
    
# home page for both staff and customers defined by user permissions
def index(request): 
    vendors = Vendor.objects.all()
    product = Product.objects.all()
    if request.method == 'POST':
        form = BroadcastForm(request.POST)
        if form.is_valid():
            form.save()
            title = form.cleaned_data.get('title')
            messages.success(request, f'broadcast added')
            return redirect('index')
        
    else:
        form = BroadcastForm()

    suppliers = Vendor.objects.all()
    sent_msgs = Message.objects.filter(email_to = request.user.email)
    orders = Order.objects.all()

    total_customers = suppliers.count()
    total_messages = sent_msgs.count()
    total_products = product.count()
    total_orders = orders.count()
    


    context = {
        'vendors': vendors,
        'product': product,
        'total_customers': total_customers,
        'room_name': "broadcast",
        'total_messages': total_messages,
        'form': form,
        'total_products':total_products,
        'total_orders': total_orders,
        'view_msg':Message.objects.filter(email_to = request.user.email),
      
    }
    return render(request, 'skeleton/index.html', context)

@login_required(login_url='login')
def products(request,):
    # fetching all the data in the products table
    #stocks = Product.objects.raw('SELECT * FROM dashboard_product')
    context = {
        'stocks': Product.objects.filter(vendor=request.user.vendor),

    }
    return render(request, 'skeleton/products.html', context)

@login_required(login_url='login')
def viewMessages(request):
    view_msg = Message.objects.filter(email_to = request.user.email)
    context = {
        'view_msg': view_msg,
    }
    return render(request, 'skeleton/messages.html', context)


@login_required(login_url='login')
def myMessages(request):
    view_msg = RepliedMessage.objects.filter(email = request.user.email)
    context = {
        'view_msg': view_msg,
    }
    return render(request, 'skeleton/customer_messages.html', context)

# reply messages sent user customers
@login_required(login_url='login')
def replyMessages(request, key):
    if request.method == 'POST':
        replied = RepliedMessage()
        replied.user = request.user.vendor
        replied.email = request.POST.get('email')
        replied.subject = request.POST.get('subject')
        replied.message = request.POST.get('message')
        replied_message(replied.user, replied.email, replied.subject, replied.message)
        return redirect('messages')

    context = {
        'reply': Message.objects.get(id=key), }
    return render(request, 'skeleton/reply_msg.html', context)


@login_required(login_url='login')
def viewMessage(request, key):
    context = {
        'view': RepliedMessage.objects.get(id=key), }
    return render(request, 'skeleton/view_msg.html', context)

# add stock products
@login_required(login_url='login')
def addProducts(request):
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            product = form.save(commit=True)
            product.vendor = request.user.vendor
            product.slug = slugify(product.title)
            form.save()
            title = form.cleaned_data.get('title')
            messages.success(request, f'{title} has been added')
            return redirect('products')
    else:
        form = ProductForm()
    context = {
        'form': form
    }
    return render(request, 'skeleton/add_products.html', context)

## supplier inventory page
@login_required(login_url='login')
def supplier_Inventory(request):
    vendor = request.user.vendor
    
    products = vendor.products.all()
    orders = vendor.orders.all()
    messages = Message.objects.filter(email_to=request.user.email)
    
    total_orders = orders.count()
    total_products = products.count()
    total_messages = messages.count()
    
    for order in orders:
        order.vendor_amount = 0
        order.vendor_paid_amount = 0
        order.fully_paid = True

        for item in order.items.all():
            if item.vendor == request.user.vendor:
                if item.vendor_paid:
                    order.vendor_paid_amount += item.get_total_price()
                else:
                    order.vendor_amount += item.get_total_price()
                    order.fully_paid = False
    context = {
        'vendor': vendor,
        'products': products,
        'orders': orders,
        'total_orders':total_orders,
        'total_products':total_products,
        'total_messages':total_messages,
   
    }
    return render(request, 'skeleton/account.html', context)


## customer inventory page
@login_required(login_url='login')
def customerInventory(request):
    
    get_budget = Budget.objects.filter(user=request.user.customer).aggregate(Sum('amount'))['amount__sum'] or 0
    get_expenses = Order.objects.filter(user=request.user.customer).aggregate(Sum('paid_amount'))['paid_amount__sum'] or 0
    
    
    calculate_expenses = get_budget - get_expenses
    
    if request.method == 'POST':
        budget = Budget()
        budget.user = request.user.customer
        budget.currency = request.POST.get('currency')
        budget.amount = request.POST.get('amount')
        budget_saved(budget.user, budget.currency, budget.amount)
        return redirect('inventory-account')
    
    context = {
        'calculate_expenses': calculate_expenses,
        'get_budget':get_budget,
        'get_expenses':get_expenses,
    }
    
    return render(request, 'skeleton/customer_inventory.html', context)



## add supplier
@login_required(login_url='login')
def addSupplier(request):
    if request.method =='POST':
        form = SupplierForm(request.POST)
        if form.is_valid():
            user = form.save()
            #supplier = Supplier.object.create(name = user.username, first_name = user.first_name, last_name = user.last_name, email = user.email)
            
            return redirect('customers')
    else :
        form = SupplierForm()
    context = {
        'form': form,
    }
    return render(request, 'skeleton/add_supplier.html', context)


# add users
@login_required(login_url='login')
def addUsers(request):
    if request.method == 'POST':
        form = CreateUserForm(request.POST)
        if form.is_valid():
            form.save()
            title = form.cleaned_data.get('username')
            messages.success(request, f'{title} has been added')
            return redirect('add_users')
    else:
        form = CreateUserForm()
    context = {
        'form': form
    }
    return render(request, 'skeleton/add_customers.html', context)

class CustomersView(TemplateView):
    template_name = 'skeleton/customer_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        customers = Vendor.objects.all()
        context['customers'] = customers
        return context


# view item details for customer


# view products in cart

# place the order and submit
@login_required(login_url='login')
def cart_details(request):
    cart = Cart(request)

    # If Checkout
    if request.method == 'POST':
        form = Order()
       # amount=int(cart.get_total_cost() * 100), # Amount in Cents
        form.user = request.user.customer
        form.pharmacy_name = request.POST.get('pharmacy_name')#changed first_name
        form.contact_person = request.POST.get('contact_person')#changed last_name
        form.email = request.POST.get('email')
        form.phone = request.POST.get('phone')
        form.address = request.POST.get('address')
        
        #removed form.first& last name
        order = checkout(request, form.user, form.pharmacy_name, form.contact_person, form.email, form.phone, form.address, cart.get_total_cost())
        cart.clear()
        return redirect('success')

    remove_from_cart = request.GET.get('remove_from_cart', '')
    change_quantity = request.GET.get('change_quantity', '')
    quantity = request.GET.get('quantity', 0)

    if remove_from_cart:
        cart.remove(remove_from_cart)
        return redirect('my_cart')
    
    if change_quantity:
        cart.add(change_quantity, quantity, True)
        return redirect('my_cart')
    
    context ={
        
    }   
    return render(request, 'skeleton/my_cart.html', context)

def success(request):
    return render(request, 'skeleton/success.html')


## view orders admin
class AdminOrders(TemplateView):
    template_name= 'skeleton/admin_dash.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        vendor = self.request.user.vendor
        context["orders"] = vendor.orders.all()
        return context
    
## view orders customer
class CustomerOrders(TemplateView):
    template_name= 'skeleton/customer_order_list.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        #changed line below        please comment when done
        customer = self.request.user.customer
        #changed line below
        context["orders"] =Order.objects.filter(user = self.request.user)
        #context["orders"] =Order.objects.filter(user = self.request.user)
        return context

# view order details
class SupplierOrderDetails(DetailView):
    template_name= 'skeleton/supplier_order_detail.html'
    model = Order
    context_object_name = 'details'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status"] = ORDER_STATUS
        return context
    
class CustomerOrderDetails(DetailView):
    template_name= 'skeleton/customer_order_detail.html'
    model = Order
    context_object_name = 'details'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status"] = ORDER_STATUS
        return context
    
class ChangeStatusView(View):
    def post(self, request, *args, **kwargs):
        order_id = self.kwargs['pk']
        order_obj = Order.objects.get(id=order_id)
        new_status = request.POST.get('status')
        order_obj.order_status = new_status
        order_obj.save()
        return redirect(reverse_lazy('s_order_detail',kwargs={'pk': order_id}))

# update stock
@login_required(login_url='login')
def update(request, key):
    stock = Product.objects.get(id=key)
    if request.method == 'POST':
        form = ProductForm(request.POST, instance=stock)
        if form.is_valid():
            form.save()
            return redirect('products')
    else:
        form = ProductForm(instance=stock)
    context = {
        'form': form,
    }
    return render(request, 'skeleton/update.html', context)

# update user info
@login_required(login_url='login')
def updateUser(request, key):
    stock = User.objects.get(id=key)
    if request.method == 'POST':
        form = CreateUserForm(request.POST, instance=stock)
        if form.is_valid():
            form.save()
            return redirect('customers')
    else:
        form = CreateUserForm(instance=stock)
    context = {
        'form': form,
    }
    return render(request, 'skeleton/update_user.html', context)

@login_required(login_url='login')
def updateSupplierAccount(request):
    vendor = Vendor.objects.get(username = request.user.username)
    if request.method == 'POST':
        form = SupplierForm(request.POST, instance=vendor)
        if form.is_valid():
            form.save()
            return redirect('index')
    else:
        form = SupplierForm(instance=vendor)
    context = {
        'form': form,
    }
    return render(request, 'skeleton/supplier_update_acc.html', context)

# delete stock form database
@login_required(login_url='login')
def delete(request, key):
    stock = Product.objects.get(id=key)
    if request.method == 'POST':
        stock.delete()
        return redirect('products')
    return render(request, 'skeleton/delete.html')

# delete order record
@login_required(login_url='login')
def deleteOrder(request, pk):
    order = Order.objects.get(id=pk)
    if request.method == 'POST':
        order.delete()
        return redirect('admin_dash')
    return render(request, 'skeleton/delete_order.html')


# reset budget
@login_required(login_url='login')
def resetBudget(request):
    reset = Budget.objects.filter(user = request.user)
    if request.method == 'POST':
        reset.delete()
        return redirect('inventory-account')
    return render(request, 'skeleton/reset_budget.html')

# customer order summary
class ProductDetailView(DetailView):
    template_name = 'skeleton/order_summary.html'
    model = Order
    context_object_name = 'ord_obj'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        url_slug = self.kwargs['slug']
        product = Product.objects.get(slug=url_slug)
        product.view_count += 1
        product.save()
        context['product'] = product
        return context

### register customers
def register(request):
    if request.method == 'POST':
        form = CreateUserForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('login')
    else :
        form = CreateUserForm()
        
    context = {
        'form': form,
    }
    return render(request, 'users/register.html', context)

### login action
def login(request):
    if request.user.is_authenticated:
        return redirect('index')
    
    return render(request, 'users/login.html')

## logout action
def logout(request):
    return render(request, 'users/logout.html')

