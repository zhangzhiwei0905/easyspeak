/**
 * EasySpeak - Library Page (内容库)
 * Browse all historical daily push content with search, filter, and pagination.
 */

const api = require('../../utils/api')
const storage = require('../../utils/storage')

const WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

function formatDateDisplay(dateStr) {
  if (!dateStr) return ''
  var parts = dateStr.split('-')
  return parseInt(parts[1]) + '月' + parseInt(parts[2]) + '日'
}

function getWeekday(dateStr) {
  if (!dateStr) return ''
  var d = new Date(dateStr + 'T00:00:00')
  return WEEKDAYS[d.getDay()]
}

function getDateLabel(dateStr) {
  if (!dateStr) return ''
  return formatDateDisplay(dateStr) + ' ' + getWeekday(dateStr)
}

/**
 * Group items by date string.
 * Input: [{..., date: '2026-04-15'}, ...]
 * Output: [{ date: '2026-04-15', label: '4月15日 周二', items: [...] }, ...]
 */
function groupByDate(items) {
  var groups = []
  var groupMap = {}

  items.forEach(function (item) {
    var date = item.date || ''
    if (!groupMap[date]) {
      var group = {
        date: date,
        label: getDateLabel(date),
        items: []
      }
      groupMap[date] = group
      groups.push(group)
    }
    groupMap[date].items.push(item)
  })

  return groups
}

Page({
  data: {
    // Search
    searchPlaceholder: '搜索短语/单词/主题...',

    // Filter tabs
    filterTabs: [
      { key: 'all', label: '全部' },
      { key: 'morning', label: '☀️ 生活场景' },
      { key: 'evening', label: '🌙 休闲话题' }
    ],
    activeFilter: 'all',

    // Loading states
    loading: true,
    refreshing: false,
    loadingMore: false,

    // Pagination
    page: 1,
    pageSize: 10,
    hasMore: true,

    // Raw list from API
    rawItems: [],

    // Grouped list (for rendering)
    dateGroups: [],

    // Empty / error
    isEmpty: false,
    error: false,
    errorMsg: ''
  },

  onLoad: function () {
    this._loadData()
  },

  onShow: function () {
    // Refresh data when page becomes visible (e.g., back from detail)
  },

  onPullDownRefresh: function () {
    var self = this
    self.setData({
      refreshing: true,
      page: 1,
      hasMore: true,
      rawItems: [],
      dateGroups: []
    })
    self._fetchPage(1).then(function () {
      wx.stopPullDownRefresh()
    }).catch(function () {
      wx.stopPullDownRefresh()
    })
  },

  onReachBottom: function () {
    if (this.data.loadingMore || !this.data.hasMore || this.data.loading) return
    this._loadMore()
  },

  onShareAppMessage: function () {
    return {
      title: 'EasySpeak · 内容库',
      path: '/pages/library/library'
    }
  },

  // ========================
  // Data Loading
  // ========================

  _loadData: function () {
    var self = this
    self.setData({
      loading: true,
      page: 1,
      hasMore: true,
      rawItems: [],
      dateGroups: [],
      isEmpty: false,
      error: false
    })
    self._fetchPage(1)
  },

  _fetchPage: function (page) {
    var self = this
    var params = {
      page: page,
      size: self.data.pageSize
    }

    // Add filter
    var filter = self.data.activeFilter
    if (filter !== 'all') {
      params.time_slot = filter
    }

    return api.get('/daily/list', params)
      .then(function (data) {
        console.log('[Library] API response page', page, ':', data)

        // API might return { items: [...], total: N, page: N, size: N }
        // or { items: [...], has_more: bool }
        var items = data.items || data.data || data.results || []
        var total = data.total || 0
        var hasMore = data.has_more !== undefined
          ? data.has_more
          : (page * self.data.pageSize < total)

        // Normalize each item
        var normalizedItems = items.map(function (item) {
          return {
            id: item.id,
            date: item.date || '',
            timeSlot: item.time_slot || 'morning',
            themeZh: item.theme_zh || '',
            themeEn: item.theme_en || '',
            phraseCount: item.phrase_count || item.phrases_count || 5,
            wordCount: item.word_count || item.words_count || 20,
            studied: !!(item.studied || item.has_studied),
            mastery: item.mastery || item.mastery_level || 0
          }
        })

        // Merge with existing items or replace
        var rawItems
        if (page === 1) {
          rawItems = normalizedItems
        } else {
          rawItems = self.data.rawItems.concat(normalizedItems)
        }

        var dateGroups = groupByDate(rawItems)

        self.setData({
          rawItems: rawItems,
          dateGroups: dateGroups,
          page: page,
          hasMore: hasMore,
          loading: false,
          refreshing: false,
          loadingMore: false,
          isEmpty: rawItems.length === 0,
          error: false
        })
      })
      .catch(function (err) {
        console.error('[Library] Fetch failed:', err)
        self.setData({
          loading: false,
          refreshing: false,
          loadingMore: false,
          error: page === 1,
          errorMsg: err.message || '加载失败',
          isEmpty: page === 1 && self.data.rawItems.length === 0
        })
      })
  },

  _loadMore: function () {
    var self = this
    var nextPage = self.data.page + 1
    self.setData({ loadingMore: true })
    self._fetchPage(nextPage)
  },

  // ========================
  // Event Handlers
  // ========================

  onSearchFocus: function () {
    wx.navigateTo({
      url: '/pages/search/search'
    })
  },

  onFilterChange: function (e) {
    var filter = e.currentTarget.dataset.filter
    if (filter === this.data.activeFilter) return
    this.setData({
      activeFilter: filter
    })
    // Reload data with new filter
    this._loadData()
  },

  onContentTap: function (e) {
    var id = e.currentTarget.dataset.id
    if (id) {
      wx.navigateTo({
        url: '/pages/detail/detail?id=' + id
      })
    }
  },

  onRetry: function () {
    this._loadData()
  }
})
