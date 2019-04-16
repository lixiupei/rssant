import gzip

from django.utils import timezone

from .exceptions import FeedExistsException
from .helper import Model, ContentHashMixin, models, optional, JSONField, User, extract_choices


class FeedStatus:
    """
    1. 用户输入URL，直接匹配到已有的Feed，status=ready
    2. 用户输入URL，无匹配, status=pending
       爬虫开始Finder, status=updating
       找到内容，status=ready，没找到, status=error
    3. 定时器扫描，Feed加入队列, status=pending
       爬虫开始抓取, status=updating
       更新内容, status=ready，更新失败 status=error
    """
    PENDING = 'pending'
    UPDATING = 'updating'
    READY = 'ready'
    ERROR = 'error'


FEED_STATUS_CHOICES = extract_choices(FeedStatus)


FEED_DETAIL_FIELDS = [
    'feed__encoding',
    'feed__etag',
    'feed__last_modified',
    'feed__content_length',
    'feed__content_hash_base64',
]


class Feed(Model, ContentHashMixin):
    """订阅的最新数据"""
    class Meta:
        indexes = [
            models.Index(fields=["url"]),
        ]

    class Admin:
        display_fields = ['status', 'title', 'url']

    url = models.TextField(unique=True, help_text="供稿地址")
    status = models.CharField(
        max_length=20, choices=FEED_STATUS_CHOICES, default=FeedStatus.PENDING, help_text='状态')
    # RSS解析内容
    title = models.CharField(max_length=200, **optional, help_text="标题")
    link = models.TextField(**optional, help_text="网站链接")
    author = models.CharField(max_length=200, **optional, help_text="作者")
    icon = models.TextField(**optional, help_text="网站Logo或图标")
    description = models.TextField(**optional, help_text="描述或小标题")
    version = models.CharField(max_length=200, **optional, help_text="供稿格式/RSS/Atom")
    dt_updated = models.DateTimeField(help_text="更新时间")
    # RSS抓取相关的状态
    dt_created = models.DateTimeField(auto_now_add=True, help_text="创建时间")
    dt_checked = models.DateTimeField(**optional, help_text="最近一次检查同步时间")
    dt_synced = models.DateTimeField(**optional, help_text="最近一次同步时间")
    encoding = models.CharField(max_length=200, **optional, help_text="编码")
    etag = models.CharField(
        max_length=200, **optional, help_text="HTTP response header ETag")
    last_modified = models.CharField(
        max_length=200, **optional, help_text="HTTP response header Last-Modified")
    content_length = models.IntegerField(
        **optional, help_text='length of content')
    # 其他
    total_storys = models.IntegerField(**optional, default=0, help_text="Total storys")

    def to_dict(self, detail=False):
        ret = dict(
            status=self.status,
            url=self.url,
            title=self.title,
            link=self.link,
            author=self.author,
            icon=self.icon,
            description=self.description,
            version=self.version,
            dt_updated=self.dt_updated,
            dt_created=self.dt_created,
        )
        if detail:
            ret.update(
                total_storys=self.total_storys,
                encoding=self.encoding,
                etag=self.etag,
                last_modified=self.last_modified,
                content_length=self.content_length,
                content_hash_base64=self.content_hash_base64,
                dt_checked=self.dt_checked,
                dt_synced=self.dt_synced,
            )
        return ret


class RawFeed(Model, ContentHashMixin):
    """订阅的原始数据"""

    class Meta:
        indexes = [
            models.Index(fields=["feed", 'status_code', "dt_created"]),
            models.Index(fields=["url", 'status_code', "dt_created"]),
        ]

    class Admin:
        display_fields = ['feed_id', 'status_code', 'url']

    feed = models.ForeignKey(Feed, on_delete=models.CASCADE)
    url = models.TextField(help_text="供稿地址")
    encoding = models.CharField(max_length=200, **optional, help_text="编码")
    status_code = models.IntegerField(**optional, help_text='HTTP状态码')
    etag = models.CharField(
        max_length=200, **optional, help_text="HTTP response header ETag")
    last_modified = models.CharField(
        max_length=200, **optional, help_text="HTTP response header Last-Modified")
    headers = JSONField(
        **optional, help_text='HTTP response headers, JSON object')
    is_gzipped = models.BooleanField(
        **optional, default=False, help_text="is content gzip compressed")
    content = models.BinaryField(**optional)
    content_length = models.IntegerField(
        **optional, help_text='length of content')
    dt_created = models.DateTimeField(auto_now_add=True, help_text="创建时间")

    def set_content(self, content):
        if content and len(content) >= 1024:
            self.content = gzip.compress(content, compresslevel=9)
            self.is_gzipped = True
        else:
            self.content = content
            self.is_gzipped = False

    def get_content(self, decompress=None):
        if decompress is None:
            decompress = self.is_gzipped
        content = self.content
        if content and decompress:
            content = gzip.decompress(content)
        return content


class UserFeed(Model):
    """用户的订阅状态"""
    class Meta:
        unique_together = ('user', 'feed')
        indexes = [
            models.Index(fields=['user', 'feed']),
        ]

    class Admin:
        display_fields = ['user_id', 'feed_id', 'status', 'url']

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    feed = models.ForeignKey(Feed, on_delete=models.CASCADE, **optional)
    status = models.CharField(
        max_length=20, choices=FEED_STATUS_CHOICES, default=FeedStatus.PENDING, help_text='状态')
    url = models.TextField(help_text="用户输入的供稿地址")
    title = models.CharField(max_length=200, **optional, help_text="用户设置的标题")
    story_offset = models.IntegerField(**optional, default=0, help_text="story offset")
    dt_created = models.DateTimeField(auto_now_add=True, help_text="创建时间")
    dt_updated = models.DateTimeField(**optional, help_text="更新时间")

    def to_dict(self, detail=False):
        if self.feed_id:
            ret = self.feed.to_dict(detail=detail)
            if detail:
                num_unread_storys = self.feed.total_storys - self.story_offset
                ret.update(num_unread_storys=num_unread_storys)
        else:
            ret = dict(url=self.url, dt_updated=self.dt_updated)
        ret.update(
            id=self.id,
            user=dict(id=self.user_id),
            dt_created=self.dt_created,
        )
        ret.update(story_offset=self.story_offset)
        if self.title:
            ret.update(title=self.title)
        if (not self.status) or (self.status != FeedStatus.READY):
            ret.update(status=self.status)
        return ret

    @property
    def is_ready(self):
        return self.status and self.status == FeedStatus.READY

    @staticmethod
    def get_by_pk(pk, user_id=None, detail=False):
        q = UserFeed.objects.select_related('feed')
        if not detail:
            q = q.defer(*FEED_DETAIL_FIELDS)
        if user_id is not None:
            q = q.filter(user_id=user_id)
        user_feed = q.get(pk=pk)
        return user_feed

    @staticmethod
    def query_by_user(user_id, hints=None, detail=False, show_pending=False):
        """获取用户所有的订阅，支持增量查询

        hints: T.list(T.dict(id=T.int, dt_updated=T.datetime))
        """
        q = UserFeed.objects.filter(user_id=user_id)
        if not show_pending:
            q = q.exclude(status=FeedStatus.PENDING)
        if not hints:
            q = q.select_related('feed')
            if not detail:
                q = q.defer(*FEED_DETAIL_FIELDS)
            return list(q.all())
        hints = {x['id']: x['dt_updated'] for x in hints}
        q = q.only("id", "dt_updated")
        updates = []
        user_feeds = list(q.all())
        total = len(user_feeds)
        for user_feed in user_feeds:
            if user_feed.id not in hints:
                updates.append(user_feed.id)
            elif user_feed.dt_updated > hints[user_feed.id]:
                updates.append(user_feed.id)
        q = UserFeed.objects.filter(user_id=user_id, id__in=updates)
        if not show_pending:
            q = q.exclude(status=FeedStatus.PENDING)
        q = q.select_related('feed')
        if not detail:
            q = q.defer(*FEED_DETAIL_FIELDS)
        user_feeds = list(q.all())
        user_feeds = list(sorted(user_feeds, key=lambda x: (x.dt_updated, x.id), reverse=True))
        return total, user_feeds

    @staticmethod
    def create_by_url(url, user_id):
        feed = None
        target_url = FeedUrlMap.find_target(url)
        if target_url:
            feed = Feed.objects.filter(url=target_url).first()
        if feed:
            user_feed = UserFeed.objects.filter(user_id=user_id, feed=feed).first()
            if user_feed:
                raise FeedExistsException('already exists')
            user_feed = UserFeed(user_id=user_id, feed=feed, url=url, status=FeedStatus.READY)
        else:
            user_feed = UserFeed(user_id=user_id, url=url)
        return user_feed

    @staticmethod
    def delete_by_pk(pk, user_id=None):
        user_feed = UserFeed.get_by_pk(pk, user_id=user_id)
        user_feed.delete()

    def update_story_offset(self, offset):
        self.story_offset = offset
        self.dt_updated = timezone.now()
        self.save()

    @staticmethod
    def create_by_url_s(urls, user_id, batch_size=500):
        # 批量预查询，减少SQL查询数量，显著提高性能
        if not urls:
            return []
        url_map = FeedUrlMap.find_all_target(urls)
        feed_map = {}
        found_feeds = Feed.objects.filter(url__in=set(url_map.values())).all()
        for x in found_feeds:
            feed_map[x.url] = x
        user_feed_map = {}
        found_user_feeds = list(UserFeed.objects.filter(
            user_id=user_id, feed__in=found_feeds).all())
        for x in found_user_feeds:
            user_feed_map[x.feed_id] = x
        user_feed_bulk_creates = []
        for url in urls:
            feed = feed_map.get(url_map.get(url))
            if feed:
                if feed.id in user_feed_map:
                    continue
                user_feed = UserFeed(user_id=user_id, feed=feed, url=url, status=FeedStatus.READY)
                user_feed_bulk_creates.append(user_feed)
            else:
                user_feed = UserFeed(user_id=user_id, url=url)
                user_feed_bulk_creates.append(user_feed)
        UserFeed.objects.bulk_create(user_feed_bulk_creates, batch_size=batch_size)
        user_feeds = found_user_feeds + user_feed_bulk_creates
        user_feeds = list(sorted(user_feeds, key=lambda x: x.url))
        return user_feeds


class FeedUrlMap(Model):
    """起始 URL 到 Feed URL 直接关联，用于加速FeedFinder"""
    class Meta:
        indexes = [
            models.Index(fields=["source", "dt_created"]),
        ]

    class Admin:
        display_fields = ['source', 'target', 'dt_created']

    source = models.TextField(help_text="起始地址")
    target = models.TextField(help_text="供稿地址")
    dt_created = models.DateTimeField(auto_now_add=True, help_text="创建时间")

    @classmethod
    def find_target(cls, source):
        q = cls.objects.filter(source=source).order_by('-dt_created')
        url_map = q.first()
        if url_map:
            return url_map.target
        return None

    @classmethod
    def find_all_target(cls, source_list):
        sql = """
        SELECT DISTINCT ON (source)
            id, source, target
        FROM rssant_api_feedurlmap
        WHERE source = ANY(%s)
        ORDER BY source, dt_created DESC
        """
        url_map = {}
        items = cls.objects.raw(sql, [source_list])
        for item in items:
            url_map[item.source] = item.target
        return url_map
