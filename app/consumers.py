from channels.generic.websocket import AsyncWebsocketConsumer
import json

class SeatBookingConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_group_name = 'seat_booking'

        # Tham gia group WebSocket
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        # Rời group WebSocket
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        data = json.loads(text_data)
        seat_id = data['seat_id']
        action = data['action']  # 'reserve' hoặc 'release'

        # Gửi thông tin ghế tới group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'seat_status_update',
                'seat_id': seat_id,
                'action': action
            }
        )

    async def seat_status_update(self, event):
        # Gửi thông tin ghế tới client
        await self.send(text_data=json.dumps({
            'seat_id': event['seat_id'],
            'action': event['action']
        }))
