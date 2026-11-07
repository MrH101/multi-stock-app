from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
from .views import (
    AdminOrders,
    GeneratePdf,
    ProductDetailView,
    GeneratePdfCustomer,
    CustomersView,
    SupplierOrderDetails,
    ChangeStatusView,
    CustomerOrders,
    CustomerOrderDetails,
    PrintPdfUsers,
    PrintDetails,
    
)


urlpatterns = [
    path('index/', views.index, name='index'),##check
    path('login_success', views.login_success, name='login_success'),##check
    path('account/', views.supplier_Inventory, name= 'account'),##check
     path('inventory-account/', views.customerInventory, name='inventory-account'),##check
    path('products/', views.products , name= 'products'),##check
    path('sup-products/<int:key>/',views.viewVendorProducts, name='sup-products'),
    path('s_order_detail/<int:pk>/',SupplierOrderDetails.as_view(), name='s_order_detail'),
    path('print-details/<int:pk>/',PrintDetails.as_view(), name='print-details'),
    path('add_products/', views.addProducts , name= 'add_products'),##check
    path('messages/', views.viewMessages , name= 'messages'),##check
    path('reply_msg/<int:key>/', views.replyMessages , name= 'reply_msg'),##check
    path('view-message/<int:key>/', views.viewMessage , name= 'view-message'),##check
    path('add_users/', views.addUsers , name= 'add_users'),##check
    path('add_supplier/', views.addSupplier , name= 'add_supplier'),##check
    path('delete/<int:key>', views.delete, name= 'delete'),##check
    path('reset-budget/', views.resetBudget, name= 'reset-budget'),##check
    path('delete-order/<int:pk>/', views.deleteOrder, name='delete-order'),
    path('update/<int:key>', views.update, name='update'),##check
    path('update-user/<int:key>', views.updateUser, name='update-user'),##check
    path('update-supplier-acc/', views.updateSupplierAccount, name='update-supplier-acc'),##check
    path('my_cart/', views.cart_details, name='my_cart'),##check
    path('view-product/<slug:product_slug>/', views.viewProduct, name='view-product'),##check
    path("checkout/", views.cart_details, name="checkout"),
    path('success/', views.success, name="success"),
    path("admin_dash/", AdminOrders.as_view(), name="admin_dash"),
    path("customer-orders/", CustomerOrders.as_view(), name="customer-orders"),
    path('customer-order-details/<int:pk>/',CustomerOrderDetails.as_view(), name='customer-order-details'),
    path("customers/", CustomersView.as_view(), name="customers"),
    path('s_order_detail-<int:pk>-change', ChangeStatusView.as_view(), name='change_status'),
    path('order_summary/<slug:slug>/', ProductDetailView.as_view(), name='order_summary'),##check
    path('pdf_file/', GeneratePdf.as_view(), name='pdf_file'),##check
    path('pdf_customer/', GeneratePdfCustomer.as_view(), name='pdf_customer'),##check
    path('print-customers/', PrintPdfUsers.as_view(), name='print-customers'),##check
    path('my-messages/', views.myMessages, name='my-messages'),##check
    path('register/', views.register, name='register'),
    path('', auth_views.LoginView.as_view(template_name ='users/login.html',redirect_authenticated_user=True), name= 'login'),
    path('logout/', auth_views.LogoutView.as_view(template_name ='users/logout.html') , name= 'logout'),
    
   
]