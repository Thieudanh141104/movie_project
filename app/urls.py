from django.urls import include, path
from rest_framework.routers import DefaultRouter
from . import views
from .views import *

router = DefaultRouter()
router.register(r'users', views.UserViewSet)
router.register(r'genre', views.GenreViewSet)
router.register(r'movies', views.MovieViewSet)
router.register(r'rooms', views.RoomViewSet)
router.register(r'screenings', views.ScreeningViewSet)
router.register(r'seats', views.SeatViewSet)
router.register(r'bookings', views.BookingViewSet)
router.register(r'userseats', views.UserSeatViewSet)

urlpatterns = [
    path('api/', include(router.urls)),
    path('', views.index, name='index'),
    path('now_showing/', views.now_showing, name='now_showing'),
    path('coming_soon/', views.coming_soon, name='coming_soon'),
    path('booking', views.booking, name='booking'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('logup/', views.logup_view, name='logup'),
    path('change-password/', views.change_password, name='changepass'),
    path('schedule/', views.schedule_view, name='schedule'),
    path('history/', views.history, name='history'),
    path('e-ticket/', views.e_ticket, name='e-ticket'),
    path('search/', views.search, name='search'),
    path('details/', views.details, name='details'),
    path('forgot-password/', views.forgot_password, name='forgot_password'),
    path('reset-password/', views.reset_password, name='reset_password'),
    path('profile/', views.profile_view, name='profile'),
    path('contact/', contact_view, name='contact'),
    path("scan-qr/", views.scan_qr_page, name="scan_qr_page"),
    path("check-ticket/", views.check_ticket, name="check_ticket"),
    
    # Các endpoint cho thanh toán qua Momo
    path('api/momo/create-payment/', views.create_momo_payment, name='create_momo_payment'),
    path('api/momo/return/', views.momo_return, name='momo_return'),
    path('api/momo/ipn/', views.momo_ipn, name='momo_ipn'),
    path('payment-success/', views.index, name='payment_success'),  # Tạm thời chuyển hướng về trang chủ
    path('payment-failed/', views.index, name='payment_failed'),    # Tạm thời chuyển hướng về trang chủ
    
    # API endpoint kiểm tra và khóa ghế
    path('api/seats/check_and_lock/', views.check_and_lock_seats, name='check_and_lock'),
]



