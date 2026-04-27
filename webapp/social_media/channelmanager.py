from django_eventstream.channelmanager import DefaultChannelManager


class PostChannelManager(DefaultChannelManager):
    """Only allow authenticated users to read post-publish channels."""

    def can_read_channel(self, user, channel):
        if channel.startswith('post-'):
            return user is not None and user.is_authenticated
        return super().can_read_channel(user, channel)
