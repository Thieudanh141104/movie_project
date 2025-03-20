from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
import cloudinary
from cloudinary.uploader import upload
from django.template.context_processors import request
from pyexpat.errors import messages
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from datetime import datetime, timedelta
from django_filters.rest_framework import DjangoFilterBackend
from app.serializers import *
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from .forms import LoginForm
from django.contrib.auth.hashers import make_password, check_password
from .models import User
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import update_session_auth_hash
import uuid
from django.core.mail import send_mail
from django.urls import reverse
import json
import hmac
import hashlib
import requests
import urllib.parse
import traceback
from django.conf import settings

# Create your views here.
class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer

    @action(detail=False, methods=['post'], url_path='update-user')
    def update_user(self, request):
        email = request.data.get('email')
        username = request.data.get('username')
        file = request.FILES.get('avatar')

        # Lấy room từ database
        user = User.objects.get(email=email)

        # Nếu có file ảnh, cập nhật avatar
        if file:
            cloudinary_response = cloudinary.uploader.upload(file)
            avatar_url = cloudinary_response.get('secure_url')
            user.avatar = avatar_url

        # Cập nhật tên
        if username:
            user.username = username

        user.save()

        return Response({
            "message": "Cập nhật thành công.",
            "avatar_url": user.avatar,
            "username": user.username,
            "email": user.email,
        }, status=status.HTTP_200_OK)


class GenreViewSet(viewsets.ModelViewSet):
    queryset = Genre.objects.all()
    serializer_class = GenreSerializer

class MovieViewSet(viewsets.ModelViewSet):
    queryset = Movie.objects.all()
    serializer_class = MovieSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status']

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) | Q(genre__genre_name__icontains=search)
            )
        return queryset

class RoomViewSet(viewsets.ModelViewSet):
    queryset = Room.objects.all()
    serializer_class = RoomSerializer

class ScreeningViewSet(viewsets.ModelViewSet):
    queryset = Screening.objects.all()
    serializer_class = ScreeningSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['movie', 'screening_date']

class SeatViewSet(viewsets.ModelViewSet):
    queryset = Seat.objects.all()
    serializer_class = SeatSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['room', 'screening']

    @action(detail=False, methods=['post'])
    def check_and_lock(self, request):
        room_id = request.data.get('room_id')
        seat_numbers = request.data.get('seats', [])  # Lấy danh sách ghế từ request
        
        # Kiểm tra dữ liệu đầu vào
        if not room_id:
            return JsonResponse({'error': 'Missing room_id parameter'}, status=400)
        if not seat_numbers or not isinstance(seat_numbers, list):
            return JsonResponse({'error': 'Invalid or missing seats parameter'}, status=400)
        
        locked_seats = []
        try:
            with transaction.atomic():  # Bắt đầu giao dịch với khóa bản ghi
                # Lấy danh sách các ghế theo seat_number
                seats = Seat.objects.select_for_update().filter(
                    seat_number__in=seat_numbers,
                    room_id=room_id
                )
                
                # Kiểm tra nếu không tìm thấy ghế nào
                if not seats.exists():
                    return JsonResponse({'error': 'No seats found with the provided information'}, status=404)
                
                # Kiểm tra số lượng ghế tìm thấy so với số lượng ghế yêu cầu
                if seats.count() != len(seat_numbers):
                    missing_seats = set(seat_numbers) - set(seats.values_list('seat_number', flat=True))
                    return JsonResponse({'error': f'Some seats were not found: {", ".join(missing_seats)}'}, status=404)

                for seat in seats:
                    if seat.status != 'available':
                        raise ValidationError(f"Seat {seat.seat_number} is already booked.")

                    # Thêm ghế vào danh sách locked_seats
                    locked_seats.append({
                        'id': seat.id,
                        'seat_number': seat.seat_number,
                        'ticket_price': float(seat.ticket_price)
                    })

            # Trả về danh sách ghế đã được khóa
            return Response(locked_seats, status=status.HTTP_200_OK)

        except ValidationError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            # Log lỗi để dễ dàng debug
            traceback.print_exc()
            return Response({'error': f'An unexpected error occurred: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class BookingViewSet(viewsets.ModelViewSet):
    queryset = Booking.objects.all()
    serializer_class = BookingSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['user']  # Định nghĩa thuộc tính cho phép lọc

class UserSeatViewSet(viewsets.ModelViewSet):
    queryset = UserSeat.objects.all()
    serializer_class = UserSeatSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['booking']

def index(request):
    return render(request, 'index.html')

def now_showing(request):
    return render(request, 'now_showing.html')

def coming_soon(request):
    return render(request, 'coming_soon.html')

def search(request):
    return render(request, 'search.html')
def booking(request):
    if not request.session.get('current_user_id'):
        return redirect('login')
    return render(request, 'ticket-booking.html')
def history(request):
    user_id = request.session.get('current_user_id')
    if not user_id:
        return redirect('login')  # Điều hướng nếu chưa đăng nhập

    bookings = Booking.objects.filter(user=user_id)
    context = {
        'bookings': []
    }

    for booking in bookings:
        screening = get_object_or_404(Screening, id=booking.screening.id)
        movie = get_object_or_404(Movie, id=screening.movie.id)
        genre = get_object_or_404(Genre, id=screening.movie.genre.id)

        context['bookings'].append({
            'id': booking.id,
            'booking_time': booking.booking_time,
            'total_price': booking.total_price,
            'screening': {
                'id': screening.id,
                'screening_date': screening.screening_date,
                'screening_time': screening.screening_time,
            },
            'movie': {
                'id': movie.id,
                'title': movie.title,
                'image_ava': movie.image_ava,
                'genre': genre.genre_name,
            },
        })

    return render(request, 'history.html', context)

def e_ticket(request):
    booking_id = request.GET.get('booking_id')
    if not booking_id:
        return JsonResponse({'error': 'Missing booking_id in query parameters'}, status=400)

    booking = get_object_or_404(Booking, id=booking_id)
    screening = booking.screening
    movie = screening.movie
    room = screening.room

    user_seats = UserSeat.objects.filter(booking=booking)
    seats = []
    total_price = 0

    for user_seat in user_seats:
        seat = user_seat.seat
        seats.append({
            'seat_number': seat.seat_number,
            'ticket_price': seat.ticket_price,
        })
        total_price += seat.ticket_price

    context = {
        'booking': booking,
        'screening': screening,
        'movie': movie,
        'room': room,
        'seats': seats,
        'total_price': total_price,
    }

    # Render template với context
    return render(request, 'e-ticket.html', context)

def login_view(request):
    host_url = request.build_absolute_uri('/')
    
    # Kiểm tra redirect sau khi đăng nhập
    next_url = request.GET.get('next', host_url)
    
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']

            try:
                user = User.objects.get(email=email)
                
                # Kiểm tra xem mật khẩu có được băm hay không
                is_hashed = user.password.startswith('pbkdf2_sha256$') or user.password.startswith('bcrypt$')
                
                if is_hashed and check_password(password, user.password):
                    # Mật khẩu đã được băm và khớp
                    request.session['current_user_id'] = user.id
                    request.session['current_username'] = user.username
                    
                    # Đặt thời gian hết hạn cho phiên làm việc (2 giờ)
                    request.session.set_expiry(7200)
                    
                    # Cập nhật thời gian hoạt động
                    user.last_activity = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    user.is_active = True
                    user.save()
                    
                    return redirect(next_url)
                elif not is_hashed and user.password == password:
                    # Mật khẩu chưa được băm (legacy) - nên cập nhật thành băm
                    user.password = make_password(password)
                    user.is_active = True
                    user.last_activity = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    user.save()
                    
                    request.session['current_user_id'] = user.id
                    request.session['current_username'] = user.username
                    request.session.set_expiry(7200)
                    
                    return redirect(next_url)
                else:
                    messages.error(request, "Sai mật khẩu. Vui lòng thử lại.")
            except User.DoesNotExist:
                messages.error(request, "Không tìm thấy tài khoản với email này.")
    else:
        form = LoginForm()
    
    return render(request, 'login.html', {'form': form, 'next': next_url})


def logout_view(request):
    # Lưu URL hiện tại để sau khi đăng xuất có thể quay lại
    referer = request.META.get('HTTP_REFERER', '/')
    
    # Xóa tất cả session data
    request.session.flush()
    
    # Django logout để xóa cookie phiên làm việc
    logout(request)
    
    return redirect(referer)


def logup_view(request):
    if request.method == 'POST':
        # Nhận dữ liệu từ form
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        
        # Kiểm tra dữ liệu đầu vào
        if not username or not email or not password:
            messages.error(request, "Vui lòng điền đầy đủ thông tin.")
            return redirect('login')
            
        # Kiểm tra định dạng email
        import re
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            messages.error(request, "Email không hợp lệ.")
            return redirect('login')
            
        # Kiểm tra độ dài mật khẩu
        if len(password) < 6:
            messages.error(request, "Mật khẩu phải có ít nhất 6 ký tự.")
            return redirect('login')

        # Kiểm tra nếu email hoặc username đã tồn tại
        if User.objects.filter(email=email).exists():
            messages.error(request, "Email này đã được sử dụng. Vui lòng nhập email khác.")
            return redirect('login')
        elif User.objects.filter(username=username).exists():
            messages.error(request, "Tên đăng nhập này đã tồn tại. Vui lòng chọn tên đăng nhập khác.")
            return redirect('login')

        # Tạo đối tượng User mới
        user = User(
            username=username,
            email=email,
            password=make_password(password),  # Mã hóa mật khẩu
            is_active=True
        )
        user.save()  # Lưu người dùng vào cơ sở dữ liệu
        messages.success(request, "Đăng ký thành công! Bạn có thể đăng nhập ngay bây giờ.")
        return redirect('login')  # Chuyển hướng đến trang đăng nhập

def change_password(request):
    user_id = request.session.get('current_user_id')
    if not user_id:
        return redirect('login')  # Điều hướng nếu chưa đăng nhập
    if request.method == 'POST':
        old_password = request.POST.get('old_password')
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')

        # Lấy user hiện tại từ session
        user = User.objects.get(id=request.session['current_user_id'])

        # Kiểm tra mật khẩu cũ (so sánh mật khẩu chưa mã hóa)
        if user.password == old_password:  # Nếu mật khẩu chưa mã hóa
            pass
        else:
            messages.error(request, "Mật khẩu cũ không đúng.")
            return redirect('changepass')  # Đảm bảo đường dẫn đúng

        # Kiểm tra mật khẩu mới và xác nhận mật khẩu
        if new_password != confirm_password:
            messages.error(request, "Mật khẩu mới không khớp.")
            return redirect('changepass')

        # Lưu mật khẩu mới (không mã hóa)
        user.password = new_password
        user.save()

        messages.success(request, "Mật khẩu đã được thay đổi thành công.")
        return redirect('login')

    return render(request, 'change_pass.html')

def forgot_password(request):
    if request.method == "POST":
        email = request.POST.get('email')
        try:
            user = User.objects.get(email=email)
            reset_token = str(uuid.uuid4())  # Tạo token ngẫu nhiên
            user.reset_token = reset_token
            user.save()

            # Gửi email
            send_mail(
                'Quên mật khẩu',
                f'Xin chào {user.username},\n\nHãy sử dụng mã sau để đặt lại mật khẩu của bạn: {reset_token}',
                'danhnguyen14112004@gmail.com',
                [email],
                fail_silently=False,
            )
            messages.success(request, "Đã gửi mã xác nhận qua email!")
            return redirect('reset_password')
        except User.DoesNotExist:
            messages.error(request, "Email không tồn tại!")
    return render(request, 'forgot_passwrd.html')

def reset_password(request):
    if request.method == "POST":
        reset_token = request.POST.get('token')
        new_password = request.POST.get('password')

        try:
            user = User.objects.get(reset_token=reset_token)
            user.password = make_password(new_password)
            user.reset_token = None  # Xóa token sau khi sử dụng
            user.save()
            messages.success(request, "Mật khẩu đã được đặt lại!")
            return redirect('login')
        except User.DoesNotExist:
            messages.error(request, "Token không hợp lệ!!")
    return render(request, 'reset_passwrd.html')

def profile_view(request):
    user_id = request.session.get('current_user_id')
    if not user_id:
        return redirect('login')  # Điều hướng nếu chưa đăng nhập
    return render(request, 'pro5.html')

def schedule_view(request):
    # Lấy ngày hiện tại
    today = datetime.today().date()

    # Tạo danh sách các ngày trong tuần (5 ngày) từ hôm nay
    date_list = [today + timedelta(days=i) for i in range(5)]

    # Lấy ngày chiếu được chọn từ URL (nếu có), mặc định là hôm nay
    selected_date_str = request.GET.get('date', today.strftime('%Y-%m-%d'))  # Chuyển ngày hiện tại thành chuỗi

    try:
        # Chuyển chuỗi ngày thành đối tượng datetime.date
        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
    except ValueError:
        # Nếu không thể chuyển đổi, sử dụng ngày hiện tại
        selected_date = today

    # Lọc các screenings theo ngày được chọn
    screenings = Screening.objects.filter(screening_date=selected_date)

    # Tạo một dictionary để nhóm các khung giờ theo bộ phim
    movies = {}
    for screening in screenings:
        movie = screening.movie
        screening_time = screening.screening_time.strftime("%H:%M")

        if movie.id not in movies:
            movies[movie.id] = {
                'title': movie.title,
                'genre': movie.genre.genre_name,
                'poster': movie.image_ava,
                'times': [],
            }

        movies[movie.id]['times'].append(screening_time)

    # Chuyển đổi dữ liệu thành danh sách các bộ phim để gửi vào template
    movie_list = list(movies.values())

    # Chuyển selected_date thành chuỗi để so sánh trong template
    selected_date_str = selected_date.strftime('%Y-%m-%d')
    
    # Debug
    print(f"Selected date: {selected_date}, Selected date string: {selected_date_str}")
    for d in date_list:
        print(f"Date in list: {d}, formatted: {d.strftime('%Y-%m-%d')}")

    # Render lại template với dữ liệu cần thiết
    return render(request, 'schedule.html', {
        'movies': movie_list,
        'dates': date_list,
        'selected_date': selected_date,
        'selected_date_str': selected_date_str
    })

def details(request):
    # Lấy ngày hiện tại
    today = datetime.today().date()

    # Tạo danh sách các ngày trong tuần (5 ngày) từ hôm nay
    date_list = [today + timedelta(days=i) for i in range(5)]

    # Lấy ngày chiếu được chọn từ URL (nếu có), mặc định là hôm nay
    selected_date_str = request.GET.get('date', today.strftime('%Y-%m-%d'))
    try:
        # Chuyển chuỗi ngày thành đối tượng datetime.date
        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
    except ValueError:
        # Nếu không thể chuyển đổi, sử dụng ngày hiện tại
        selected_date = today
        selected_date_str = today.strftime('%Y-%m-%d')

    # Định dạng danh sách ngày để truyền vào template
    formatted_date_list = [d.strftime('%Y-%m-%d') for d in date_list]
    
    # Thêm log để debug
    print(f"Details view - Selected date: {selected_date}, formatted as: {selected_date_str}")
    print(f"Date list: {formatted_date_list}")

    # Lấy `movie_id` từ tham số URL
    movie_id = request.GET.get('movie_id')
    # Kiểm tra xem movie có tồn tại không
    movie = get_object_or_404(Movie, id=movie_id)

    # Lọc các screenings theo `movie_id` và ngày được chọn
    screenings = Screening.objects.filter(movie_id=movie_id, screening_date=selected_date)

    # Danh sách thời gian chiếu
    screening_times = [screening.screening_time.strftime("%H:%M") for screening in screenings]

    # Tạo dữ liệu để gửi vào template
    movie_data = {
        'id': movie.id,
        'title': movie.title,
        'genre': movie.genre.genre_name,
        'trailer': movie.trailer,
        'poster': movie.image_ava,
        'times': screening_times,
    }

    # Render template với dữ liệu
    return render(request, 'details.html', {
        'movie': movie_data,
        'dates': formatted_date_list,
        'selected_date': selected_date_str
    })

def contact_view(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        message = request.POST.get('message')

        if not name or not email:
            messages.error(request, 'Vui lòng nhập đầy đủ các trường bắt buộc.')
        else:
            contact = Contact.objects.create(
                name=name,
                email=email,
                message=message,
            )
            messages.success(request, 'Thông tin đã được gửi thành công!')
            return render(request, 'contact.html')

    return render(request, 'contact.html')

@api_view(['POST'])
def create_booking_direct(request):
    """
    Bỏ qua Momo, xác nhận đặt vé ngay lập tức
    """
    try:
        user_id = request.session.get('current_user_id')
        if not user_id:
            return Response({'error': 'Bạn cần đăng nhập để đặt vé'}, status=401)

        request_data = request.data
        amount = int(float(request_data.get('amount', 0)))
        screening_id = request_data.get('screening_id')
        room_id = request_data.get('room_id')
        seats = request_data.get('seats', [])

        if not screening_id or not room_id or not seats:
            return Response({'error': 'Thiếu thông tin cần thiết cho đặt vé'}, status=400)

        # Tạo mã đơn hàng giả lập
        timestamp = int(datetime.now().timestamp())
        order_id = f"MOVIE_{user_id}_{timestamp}_{uuid.uuid4().hex[:8]}"

        # Tạo booking mới
        booking = Booking.objects.create(
            user_id=user_id,
            screening_id=screening_id,
            total_price=amount,
            payment_method='direct'
        )

        # Cập nhật trạng thái ghế thành 'unavailable'
        seats_to_update = Seat.objects.filter(
            seat_number__in=seats,
            room_id=room_id,
            screening_id=screening_id
        )
        seats_to_update.update(status='unavailable')

        # Liên kết ghế với booking
        for seat in seats_to_update:
            UserSeat.objects.create(
                booking=booking,
                seat=seat
            )

        print(f"🚀 Đặt vé thành công: {order_id} cho user {user_id}")

        # Chuyển hướng đến e-ticket
        return Response({
            'orderId': order_id,
            'message': 'Đặt vé thành công',
            'status': 'success',
            'booking_id': booking.id
        }, status=200)

    except Exception as e:
        return Response({'error': str(e)}, status=500)

@api_view(['POST'])
def check_and_lock_seats(request):
    """
    Kiểm tra và khóa tạm thời ghế đã chọn
    """
    try:
        # Lấy dữ liệu từ request
        request_data = request.data
        print(f"check_and_lock_seats - Received data: {request_data}")
        
        # Kiểm tra dữ liệu đầu vào
        room_id = request_data.get('room_id')
        screening_id = request_data.get('screening_id') 
        seats = request_data.get('seats', [])
        
        if not room_id or not screening_id or not seats:
            return Response({
                'success': False,
                'message': 'Thiếu thông tin bắt buộc (room_id, screening_id, seats)'
            }, status=400)
            
        print(f"Processing check_and_lock for room_id: {room_id}, screening_id: {screening_id}, seats: {seats}")
        
        # Kiểm tra xem lịch chiếu có tồn tại không
        try:
            screening = Screening.objects.get(id=screening_id)
        except Screening.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Lịch chiếu không tồn tại'
            }, status=404)
            
        # Kiểm tra phòng chiếu
        try:
            room = Room.objects.get(id=room_id)
        except Room.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Phòng chiếu không tồn tại'
            }, status=404)
            
        # Kiểm tra ghế đã được đặt chưa
        seat_objects = Seat.objects.filter(room_id=room_id, seat_number__in=seats)
        if len(seat_objects) != len(seats):
            return Response({
                'success': False,
                'message': 'Một số ghế không tồn tại trong phòng này'
            }, status=400)
            
        # Kiểm tra xem ghế đã được đặt chưa (đã có booking)
        booked_seats = UserSeat.objects.filter(
            seat__in=seat_objects,
            booking__screening=screening
        ).values_list('seat__seat_number', flat=True)
        
        if booked_seats:
            return Response({
                'success': False,
                'message': f'Ghế đã được đặt: {", ".join(booked_seats)}'
            }, status=400)
            
        # Lấy giá vé của các ghế
        seat_prices = {}
        total_price = 0
        
        for seat in seat_objects:
            # Sử dụng giá vé từ bảng Seat hoặc giá mặc định nếu không có
            price = float(seat.ticket_price) if seat.ticket_price else 50
            seat_prices[seat.seat_number] = price
            total_price += price
            
        # Khóa ghế tạm thời (có thể thực hiện bằng cache/session...)
        # Ở đây chỉ giả lập bằng cách lưu vào session
        locks = request.session.get('seat_locks', {})
        
        # Tạo khóa mới với timestamp
        now = datetime.now().timestamp()
        lock_id = f"{screening_id}_{room_id}_{now}"
        
        # Lưu thông tin khóa ghế
        locks[lock_id] = {
            'room_id': room_id,
            'screening_id': screening_id,
            'seats': seats,
            'timestamp': now,
            'expires': now + 600  # Khóa trong 10 phút
        }
        
        request.session['seat_locks'] = locks
        request.session.modified = True
        
        # Trả về kết quả thành công
        return Response({
            'success': True,
            'message': 'Ghế đã được khóa tạm thời',
            'lock_id': lock_id,
            'seat_prices': seat_prices,
            'total_price': total_price,
            'seats': seats,
            'room_id': room_id,
            'screening_id': screening_id
        })
        
    except Exception as e:
        error_message = f"Exception in check_and_lock_seats: {str(e)}"
        print(error_message)
        return Response({
            'success': False,
            'message': str(e)
        }, status=500)


def scan_qr_page(request):
    """Hiển thị trang quét mã QR"""
    return render(request, "scan_qr.html")


def check_ticket(request):
    """Kiểm tra vé sau khi quét mã QR"""
    qr_code_uuid = request.GET.get("qr_code_uuid")

    try:
        booking = Booking.objects.get(qr_code_uuid=qr_code_uuid)

        if booking.is_used:
            return JsonResponse({
                "valid": False,
                "message": "❌ Vé đã sử dụng!",
                "customer": booking.user.username,
                "used_time": booking.booking_time.strftime("%H:%M, %d/%m/%Y"),
            })

        # Đánh dấu vé đã được sử dụng
        booking.is_used = True
        booking.save()

        return JsonResponse({
            "valid": True,
            "message": "✅ Vé hợp lệ!",
            "customer": booking.user.username,
            "movie": booking.screening.movie,
            "time": booking.screening.start_time.strftime("%H:%M, %d/%m/%Y"),
            "seat": "A12",  # Cập nhật nếu có thông tin ghế
            "total_price": f"{booking.total_price} VNĐ",
            "payment_method": booking.payment_method,
        })
    except Booking.DoesNotExist:
        return JsonResponse({"valid": False, "message": "🚫 Vé không hợp lệ!"})