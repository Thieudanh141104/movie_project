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
def create_momo_payment(request):
    """
    Tạo yêu cầu thanh toán qua Momo và trả về URL để chuyển hướng
    """
    try:
        # Kiểm tra người dùng đã đăng nhập chưa
        user_id = request.session.get('current_user_id')
        print(f"Current user_id from session: {user_id}")
        
        if not user_id:
            return Response({'error': 'Bạn cần đăng nhập để thanh toán'}, status=401)
        
        # ========= XỬ LÝ DỮ LIỆU TỪ REQUEST =========
        # Cách mới: Sử dụng request.data của DRF một cách an toàn
        try:
            # Lấy dữ liệu từ DRF request.data
            request_data = request.data
            print(f"request.data: {request_data}")
            
            if not request_data:
                # Fallback nếu request.data trống
                return Response({'error': 'Không có dữ liệu được gửi trong request'}, status=400)
                
            # Xử lý request data
            amount = int(float(request_data.get('amount', 0)))
            order_info = request_data.get('orderInfo', 'Thanh toán vé xem phim')
            extra_data = request_data.get('extraData', '')
            
            print(f"Đã xử lý: amount={amount}, order_info={order_info}")
            
        except ValueError as e:
            print(f"Lỗi định dạng số: {str(e)}")
            return Response({'error': f'Giá trị không hợp lệ: {str(e)}'}, status=400)
        except Exception as e:
            print(f"Lỗi đọc dữ liệu request: {str(e)}")
            return Response({'error': f'Không thể đọc dữ liệu yêu cầu: {str(e)}'}, status=400)
            
        # ========= XỬ LÝ EXTRA DATA =========
        # Xử lý extraData - giải mã nếu là chuỗi JSON
        extra_data_parsed = None
        try:
            if isinstance(extra_data, str):
                extra_data_parsed = json.loads(extra_data)
            else:
                extra_data_parsed = extra_data
                
            print(f"Parsed extraData: {extra_data_parsed}")
            
        except Exception as e:
            print(f"Error parsing extraData: {str(e)}")
            extra_data_parsed = {'raw': str(extra_data)}
            
        # ========= KIỂM TRA THÔNG TIN =========
        # Kiểm tra thông tin ghế và lịch chiếu
        screening_id = extra_data_parsed.get('screening_id')
        room_id = extra_data_parsed.get('room_id')
        seats = extra_data_parsed.get('seats', [])
        
        if not screening_id or not room_id or not seats:
            return Response({'error': 'Thiếu thông tin cần thiết cho thanh toán'}, status=400)
            
        # Kiểm tra lịch chiếu có tồn tại không
        try:
            screening = Screening.objects.get(id=screening_id)
            print(f"Found screening: {screening}")
        except Screening.DoesNotExist:
            return Response({'error': 'Lịch chiếu không tồn tại'}, status=404)
        
        # ========= XỬ LÝ AMOUNT =========
        # Nếu amount = 0, tính lại từ giá vé
        if amount <= 0 and seats:
            try:
                # Lấy tổng giá vé từ các ghế được chọn
                selected_seats = Seat.objects.filter(
                    room_id=room_id,
                    seat_number__in=seats
                )
                if selected_seats.exists():
                    # Tính tổng giá vé
                    amount = sum(float(seat.ticket_price) * 1000 for seat in selected_seats)
                    print(f"Calculated amount from seats: {amount}")
                    
                    if amount <= 0:
                        # Nếu vẫn = 0, dùng giá trị mặc định
                        amount = len(seats) * 50000  # 50,000 VND mỗi ghế
                        print(f"Using default price: {amount}")
            except Exception as e:
                print(f"Error calculating amount from seats: {str(e)}")
                # Sử dụng giá mặc định nếu có lỗi
                amount = len(seats) * 50000  # 50,000 VND mỗi ghế
                print(f"Using default price after error: {amount}")
        
        # Vẫn kiểm tra nhưng bây giờ chúng ta đã có biện pháp phòng ngừa
        if amount <= 0:
            return Response({'error': 'Số tiền thanh toán không hợp lệ'}, status=400)
        
        # ========= TẠO THÔNG TIN THANH TOÁN =========
        # Tạo mã đơn hàng ngẫu nhiên nhưng có cấu trúc rõ ràng
        timestamp = int(datetime.now().timestamp())
        order_id = f"MOVIE_{user_id}_{timestamp}_{uuid.uuid4().hex[:8]}"
        
        # URL callback sau khi thanh toán xong
        redirect_url = request.build_absolute_uri(reverse('momo_return'))
        ipn_url = request.build_absolute_uri(reverse('momo_ipn'))
        
        print(f"Redirect URL: {redirect_url}")
        print(f"IPN URL: {ipn_url}")
        
        # Các thông số cần thiết để gọi API Momo
        partner_code = settings.MOMO_PARTNER_CODE if hasattr(settings, 'MOMO_PARTNER_CODE') else "MOMO_TEST"
        access_key = settings.MOMO_ACCESS_KEY if hasattr(settings, 'MOMO_ACCESS_KEY') else "F8BBA842ECF85"
        secret_key = settings.MOMO_SECRET_KEY if hasattr(settings, 'MOMO_SECRET_KEY') else "K951B6PE1waDMi640xX08PD3vg6EkVlz"
        
        # Chuẩn bị extraData để lưu vào Momo
        momo_extra_data = json.dumps({
            'user_id': user_id,
            'screening_id': screening_id,
            'room_id': room_id,
            'seats': seats,
            'amount': amount
        })
        
        # ========= THỰC HIỆN TẠO GIAO DỊCH =========
        # Lưu thông tin yêu cầu thanh toán vào session trước
        request.session['payment_request'] = {
            'order_id': order_id,
            'amount': amount,
            'screening_id': screening_id,
            'room_id': room_id,
            'seats': seats,
            'user_id': user_id,
            'timestamp': timestamp
        }
        
        # Nếu chạy trong môi trường phát triển, trả về mô phỏng để test
        if request.get_host() in ['localhost:8000', '127.0.0.1:8000']:
            print("Simulating Momo payment in development mode...")
            
            # Trả về giả lập URL thanh toán cho môi trường phát triển
            mock_url = request.build_absolute_uri(f"/api/momo/return?resultCode=0&orderId={order_id}&message=Success")
            return Response({
                'payUrl': mock_url,
                'orderId': order_id,
                'message': 'Mô phỏng thanh toán thành công (môi trường phát triển)'
            })
        
        # Dữ liệu gửi đến Momo
        encoded_extra_data = urllib.parse.quote(momo_extra_data)
        raw_data = {
            'partnerCode': partner_code,
            'accessKey': access_key,
            'requestId': order_id,
            'amount': amount,
            'orderId': order_id,
            'orderInfo': order_info,
            'returnUrl': redirect_url,
            'notifyUrl': ipn_url,
            'requestType': 'captureMoMoWallet',
            'extraData': encoded_extra_data
        }
        
        # Tạo chữ ký (signature)
        raw_signature = "accessKey=" + access_key + "&amount=" + str(amount) + "&extraData=" + \
                     encoded_extra_data + "&orderId=" + order_id + "&orderInfo=" + \
                     raw_data['orderInfo'] + "&partnerCode=" + partner_code + "&requestId=" + \
                     order_id + "&returnUrl=" + redirect_url
        
        h = hmac.new(bytes(secret_key, 'utf-8'), bytes(raw_signature, 'utf-8'), hashlib.sha256)
        signature = h.hexdigest()
        raw_data['signature'] = signature
        
        # Gọi API của Momo
        momo_endpoint = "https://test-payment.momo.vn/v2/gateway/api/create"
        
        try:
            print(f"Calling Momo API with data: {raw_data}")
            
            response = requests.post(momo_endpoint, json=raw_data)
            print(f"Momo API response status: {response.status_code}")
            print(f"Momo API response text: {response.text}")
            
            if response.status_code == 200:
                response_data = response.json()
                
                # Log thông tin giao dịch
                print(f"Payment request created: {order_id} for user {user_id}, amount: {amount}")
                
                # Trả về URL thanh toán và các thông tin liên quan
                return Response({
                    'payUrl': response_data.get('payUrl'),
                    'orderId': order_id,
                    'message': response_data.get('message')
                })
            else:
                error_message = f"Momo API error: {response.status_code} - {response.text}"
                print(error_message)
                return Response({'error': 'Không thể kết nối với Momo', 'details': error_message}, status=502)
        except requests.exceptions.RequestException as e:
            error_message = f"Network error when calling Momo API: {str(e)}"
            print(error_message)
            return Response({'error': 'Lỗi mạng khi kết nối đến Momo', 'details': error_message}, status=500)
        except Exception as e:
            error_message = f"Exception when calling Momo API: {str(e)}"
            print(error_message)
            return Response({'error': str(e), 'details': error_message}, status=500)
    except Exception as e:
        error_message = f"Exception in create_momo_payment: {str(e)}"
        print(error_message)
        return Response({'error': str(e), 'details': error_message}, status=400)

@api_view(['GET'])
def momo_return(request):
    """
    Xử lý kết quả trả về từ Momo sau khi người dùng thanh toán xong
    """
    try:
        # Lấy các tham số trả về từ Momo
        result_code = request.GET.get('resultCode')
        order_id = request.GET.get('orderId')
        message = request.GET.get('message', '')
        
        print(f"Momo return callback received: result_code={result_code}, order_id={order_id}, message={message}")
        print(f"Full query params: {dict(request.GET.items())}")
        
        # Lấy thông tin thanh toán từ session
        payment_request = request.session.get('payment_request', {})
        print(f"Payment request from session: {payment_request}")
        
        user_id = payment_request.get('user_id')
        screening_id = payment_request.get('screening_id')
        room_id = payment_request.get('room_id')
        seats = payment_request.get('seats', [])
        amount = payment_request.get('amount', 0)
        
        # Kiểm tra kết quả thanh toán
        if result_code == '0':  # Thanh toán thành công
            print("Payment successful, processing booking...")
            try:
                # Tự động xử lý tạo booking nếu thanh toán thành công
                if user_id and screening_id and room_id and seats:
                    print(f"Creating booking for user={user_id}, screening={screening_id}, room={room_id}, seats={seats}")
                    
                    # Debug: Kiểm tra tất cả ghế trong phòng
                    all_seats_in_room = Seat.objects.filter(room_id=room_id)
                    print(f"All seats in room {room_id}: {list(all_seats_in_room.values_list('seat_number', flat=True))}")
                    
                    # Khóa và cập nhật trạng thái ghế
                    seats_to_update = Seat.objects.filter(
                        seat_number__in=seats,
                        room_id=room_id,
                        screening_id=screening_id
                    )
                    
                    print(f"Found {seats_to_update.count()} seats to update")
                    print(f"Query parameters: seat_number__in={seats}, room_id={room_id}, screening_id={screening_id}")
                    
                    # Tạo booking mới trước
                    booking = Booking.objects.create(
                        user_id=user_id,
                        screening_id=screening_id,
                        total_price=amount / 1000,  # Chuyển đổi lại từ VND sang đơn vị hiển thị (.000đ)
                        payment_method='momo'
                    )
                    
                    print(f"Created booking with ID: {booking.id}")
                    
                    # Nếu không tìm thấy ghế, kiểm tra ghế theo chỉ room_id
                    if seats_to_update.count() == 0:
                        print("Không tìm thấy ghế với screening_id, thử tìm ghế chỉ với room_id")
                        room_seats = Seat.objects.filter(
                            seat_number__in=seats,
                            room_id=room_id
                        )
                        print(f"Tìm thấy {room_seats.count()} ghế chỉ với room_id")
                        
                        # Nếu tìm thấy ghế trong phòng, cập nhật screening_id cho các ghế này
                        if room_seats.exists():
                            print(f"Cập nhật screening_id={screening_id} cho các ghế đã tìm thấy")
                            for seat in room_seats:
                                # Tạo bản sao ghế mới với screening_id mới
                                try:
                                    seat_copy = Seat.objects.get(
                                        seat_number=seat.seat_number,
                                        room_id=room_id,
                                        screening_id=screening_id
                                    )
                                    print(f"Ghế {seat.seat_number} đã tồn tại với screening_id={screening_id}")
                                except Seat.DoesNotExist:
                                    seat_copy = Seat.objects.create(
                                        seat_number=seat.seat_number,
                                        room_id=room_id,
                                        screening_id=screening_id,
                                        status='available',
                                        ticket_price=seat.ticket_price
                                    )
                                    print(f"Đã tạo ghế mới {seat.seat_number} với screening_id={screening_id}")
                            
                            # Tìm lại ghế sau khi đã cập nhật
                            seats_to_update = Seat.objects.filter(
                                seat_number__in=seats,
                                room_id=room_id,
                                screening_id=screening_id
                            )
                            print(f"Sau khi cập nhật, tìm thấy {seats_to_update.count()} ghế để cập nhật")
                    
                    # Nếu có ghế, cập nhật trạng thái và liên kết với booking
                    if seats_to_update:
                        # Cập nhật trạng thái ghế thành 'unavailable'
                        seats_to_update.update(status='unavailable')
                        
                        # Liên kết ghế với booking
                        for seat in seats_to_update:
                            user_seat = UserSeat.objects.create(
                                booking=booking,
                                seat=seat
                            )
                            print(f"Linked seat {seat.seat_number} to booking")
                    else:
                        # Tạo ghế mới cho booking nếu không tìm thấy ghế nào
                        print("Không tìm thấy ghế nào sau khi cố gắng tạo. Tạo ghế mới cho booking.")
                        for seat_number in seats:
                            # Tạo ghế mới
                            new_seat = Seat.objects.create(
                                seat_number=seat_number,
                                room_id=room_id,
                                screening_id=screening_id,
                                status='unavailable',
                                ticket_price=50  # Giá mặc định
                            )
                            print(f"Tạo ghế mới {seat_number} cho booking.")
                            
                            # Liên kết ghế với booking
                            user_seat = UserSeat.objects.create(
                                booking=booking,
                                seat=new_seat
                            )
                            print(f"Linked new seat {seat_number} to booking")
                    
                    # Xóa thông tin từ session
                    if 'payment_request' in request.session:
                        del request.session['payment_request']
                        print("Deleted payment_request from session")
                    
                    # Chuyển hướng đến trang e-ticket
                    redirect_url = f'/e-ticket?booking_id={booking.id}'
                    print(f"Redirecting to: {redirect_url}")
                    return redirect(redirect_url)
                else:
                    missing_info = []
                    if not user_id: missing_info.append("user_id")
                    if not screening_id: missing_info.append("screening_id")
                    if not room_id: missing_info.append("room_id")
                    if not seats: missing_info.append("seats")
                    
                    print(f"Missing booking information: {', '.join(missing_info)}")
                    messages.error(request, f"Thiếu thông tin cần thiết để tạo đơn hàng: {', '.join(missing_info)}")
                    return redirect('payment_failed')
            except Exception as e:
                print(f"Error creating booking after Momo payment: {str(e)}")
                print(f"Traceback: {traceback.format_exc()}")
                messages.error(request, f"Thanh toán thành công nhưng không thể tạo đơn hàng: {str(e)}")
                return redirect('payment_failed')
                
            # Thanh toán thành công nhưng không có đủ thông tin để tạo booking
            messages.success(request, 'Thanh toán thành công! Đang tạo đơn hàng...')
            return redirect('payment_success')
        else:
            # Thanh toán thất bại
            error_message = f"Thanh toán không thành công: {message} (Mã lỗi: {result_code})"
            print(f"Payment failed: {error_message}")
            messages.error(request, error_message)
            return redirect('payment_failed')
    except Exception as e:
        print(f"Exception in momo_return: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        messages.error(request, f"Lỗi xử lý kết quả thanh toán: {str(e)}")
        return redirect('payment_failed')

@api_view(['POST'])
def momo_ipn(request):
    """
    Xử lý thông báo thanh toán từ Momo (IPN - Instant Payment Notification)
    """
    try:
        # Parse dữ liệu IPN từ Momo
        data = json.loads(request.body)
        
        # Lấy các thông tin cần thiết
        result_code = data.get('resultCode')
        order_id = data.get('orderId')
        transaction_id = data.get('transId')
        amount = data.get('amount')
        extra_data = data.get('extraData', '')
        
        # Giải mã extraData
        try:
            decoded_extra_data = urllib.parse.unquote(extra_data)
            extra_data_json = json.loads(decoded_extra_data)
            user_id = extra_data_json.get('user_id')
            screening_id = extra_data_json.get('screening_id')
            room_id = extra_data_json.get('room_id')
            seats = extra_data_json.get('seats', [])
        except:
            extra_data_json = {}
            user_id = None
            screening_id = None
            room_id = None
            seats = []
        
        # Kiểm tra kết quả thanh toán
        if result_code == '0':  # Thanh toán thành công
            # Xử lý tương tự như trong hàm momo_return, nhưng không chuyển hướng
            try:
                if user_id and screening_id and room_id and seats:
                    # Kiểm tra xem booking đã tồn tại chưa
                    existing_booking = Booking.objects.filter(
                        user_id=user_id,
                        screening_id=screening_id,
                        payment_method='momo'
                    ).order_by('-booking_time').first()
                    
                    if existing_booking:
                        # Nếu đã có booking, không tạo lại
                        return Response({'message': 'Booking already exists', 'booking_id': existing_booking.id})
                    
                    # Cập nhật trạng thái ghế
                    seats_to_update = Seat.objects.filter(
                        seat_number__in=seats,
                        room_id=room_id,
                        screening_id=screening_id
                    )
                    
                    seats_to_update.update(status='unavailable')
                    
                    # Tạo booking mới
                    booking = Booking.objects.create(
                        user_id=user_id,
                        screening_id=screening_id,
                        total_price=amount / 1000,
                        payment_method='momo'
                    )
                    
                    # Liên kết ghế với booking
                    for seat in seats_to_update:
                        UserSeat.objects.create(
                            booking=booking,
                            seat=seat
                        )
                    
                    return Response({'message': 'Success', 'booking_id': booking.id})
            except Exception as e:
                print(f"IPN Error: {str(e)}")
                return Response({'message': f'Error: {str(e)}'})
        
        return Response({'message': 'Received'})
    except Exception as e:
        print(f"IPN Exception: {str(e)}")
        return Response({'message': f'Exception: {str(e)}'})

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