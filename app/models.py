from django.db import models
from django.contrib.auth.models import User

class User(models.Model):
    username = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    last_activity = models.CharField(max_length=100, blank=True, null=True)
    reset_token = models.CharField(max_length=100, blank=True, null=True)
    avatar = models.TextField('file', null=True, blank=True)

    def __str__(self):
        return self.username

class Genre(models.Model):
    genre_name = models.CharField(max_length=255)

    def __str__(self):
        return self.genre_name

class Movie(models.Model):
    title = models.CharField(max_length=255)
    genre = models.ForeignKey(Genre, on_delete=models.CASCADE)
    duration = models.IntegerField()  # in minutes
    description = models.TextField()
    image_ava = models.TextField()
    image_cover = models.TextField()
    trailer = models.TextField()
    status = models.CharField()

    def __str__(self):
        return self.title

class Contact(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Room(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class Screening(models.Model):
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE)
    screening_date = models.DateField(null=True, blank=True)
    screening_time = models.TimeField(null=True, blank=True)
    room = models.ForeignKey(Room, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.movie.title} at {self.screening_time}"


class Seat(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    seat_number = models.CharField(max_length=10)  # e.g., A1, B2, etc.
    status = models.CharField(max_length=50)  # available, booked
    ticket_price = models.DecimalField(max_digits=6, decimal_places=2)
    screening = models.ForeignKey(Screening, on_delete=models.CASCADE, default=1)

    def __str__(self):
        return f"{self.seat_number} in {self.room.name}"


class Booking(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    screening = models.ForeignKey(Screening, on_delete=models.CASCADE)
    booking_time = models.DateTimeField(auto_now_add=True)
    total_price = models.DecimalField(max_digits=6, decimal_places=2)
    payment_method = models.CharField(max_length=50, default='card')

    def __str__(self):
        return f"Booking by {self.user.username} in {self.screening.room.name} with {self.total_price}"

class UserSeat(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, null=True, blank=True)
    seat = models.ForeignKey(Seat, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.booking.id} vs {self.seat.seat_number}"
