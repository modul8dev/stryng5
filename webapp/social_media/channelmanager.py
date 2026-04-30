from django_eventstream.channelmanager import DefaultChannelManager


class MessageChannelManager(DefaultChannelManager):
    """Only allow authenticated users to read their own user channel."""

    def can_read_channel(self, user, channel):
        if channel.startswith('user-'):
            if user is None or not user.is_authenticated:
                return False
            # Users can only read their own channel
            return channel == f'user-{user.id}'
        return super().can_read_channel(user, channel)
