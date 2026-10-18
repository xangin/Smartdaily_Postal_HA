"""Constants for the Smartdaily Postal integration."""

DOMAIN = "smartdaily_postal_ha"

CONF_DEVICE_ID = "DeviceID"
CONF_COM_ID = "com_id"
CONF_CATEGORIES = "categories"
CONF_FAST_INTERVAL = "fast_interval"
CONF_SLOW_INTERVAL = "slow_interval"

CAT_PACKAGE = "package"
CAT_COLLECTION = "collection"
CAT_ANNOUNCEMENT = "announcement"
CAT_POINTS = "points"
ALL_CATEGORIES = [CAT_PACKAGE, CAT_COLLECTION, CAT_ANNOUNCEMENT, CAT_POINTS]

# 包裹、寄放物需要即時；公告、點數變化慢
FAST_CATEGORIES = {CAT_PACKAGE, CAT_COLLECTION}
SLOW_CATEGORIES = {CAT_ANNOUNCEMENT, CAT_POINTS}

DEFAULT_FAST_INTERVAL = 5  # 分鐘
DEFAULT_SLOW_INTERVAL = 60  # 分鐘

# items 屬性中「近期已取件」最多保留幾筆
MAX_CLAIMED_ITEMS = 10

# Bus 事件名稱：smartdaily_postal_ha_package / _collection / _announcement
EVENT_PACKAGE = f"{DOMAIN}_{CAT_PACKAGE}"
EVENT_COLLECTION = f"{DOMAIN}_{CAT_COLLECTION}"
EVENT_ANNOUNCEMENT = f"{DOMAIN}_{CAT_ANNOUNCEMENT}"

DEFAULT_IMAGE_URL = "https://img.smartdaily.com.tw/wordpress/smartdaily/homepage/LOGO.png"

STORAGE_VERSION = 1
