/**
 * EasySpeak - Library Page (内容库)
 * Browse all historical daily push content with search and pagination.
 */

const api = require('../../utils/api')
const storage = require('../../utils/storage')

const WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
const SEARCH_HISTORY_KEY = 'easyspeak_search_history'
const MAX_HISTORY = 10
const CATEGORY_FILTERS = [
  { key: '', label: '全部' },
  { key: 'life', label: '生活场景' },
  { key: 'travel', label: '旅行出行' },
  { key: 'work', label: '职场商务' },
  { key: 'social', label: '社交关系' },
  { key: 'shopping', label: '购物消费' },
  { key: 'health', label: '医疗健康' },
  { key: 'education', label: '学习教育' },
  { key: 'communication', label: '电话邮件' },
  { key: 'emergency', label: '紧急情况' },
  { key: 'entertainment', label: '文化娱乐' }
]

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

function groupByDate(items) {
  var groups = []
  var groupMap = {}
  items.forEach(function (item) {
    var date = item.date || ''
    if (!groupMap[date]) {
      var group = { date: date, label: getDateLabel(date), items: [] }
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
    searchFocused: false,
    searchActive: false,
    searchKeyword: '',
    searchHistory: [],
    searchThemes: [],
    searchPhrases: [],
    searchWords: [],
    searchDone: false,
    categoryFilters: CATEGORY_FILTERS,
    selectedCategory: '',

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

  _searchTimer: null,

  onLoad: function () {
    // Load search history
    var history = wx.getStorageSync(SEARCH_HISTORY_KEY) || []
    this.setData({ searchHistory: history })
    this._loadData()
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
    var params = { page: page, size: self.data.pageSize }
    if (self.data.selectedCategory) {
      params.category = self.data.selectedCategory
    }

    return api.get('/daily/list', params)
      .then(function (data) {
        var items = data.items || data.data || data.results || []
        var total = data.total || 0
        var hasMore = data.has_more !== undefined
          ? data.has_more
          : (page * self.data.pageSize < total)

 var normalizedItems = items.map(function (item) {
 return {
 id: item.id,
 date: item.date || '',
 themeZh: item.theme_zh || '',
 themeEn: item.theme_en || '',
 category: item.category || '',
 categoryZh: item.category_zh || '',
 phraseCount: item.phrase_count || item.phrases_count || 0,
 wordCount: item.word_count || item.words_count || 0,
 studied: !!(item.studied || item.has_studied),
 mastery: item.mastery || item.mastery_level || 0
 }
 })

        var rawItems = page === 1 ? normalizedItems : self.data.rawItems.concat(normalizedItems)
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
  // Search
  // ========================

  onSearchFocus: function () {
    this.setData({ searchFocused: true, searchActive: true })
  },

  onSearchBlur: function () {
    this.setData({ searchFocused: false })
  },

  onSearchInput: function (e) {
    var keyword = e.detail.value || ''
    this.setData({ searchKeyword: keyword, searchDone: false })

    // Debounce: search after 400ms of no typing
    if (this._searchTimer) clearTimeout(this._searchTimer)
    if (!keyword.trim()) {
      this.setData({ searchThemes: [], searchPhrases: [], searchWords: [], searchDone: false })
      return
    }
    var self = this
    this._searchTimer = setTimeout(function () {
      self._doSearch(keyword.trim())
    }, 400)
  },

  onSearchConfirm: function (e) {
    var keyword = (e.detail.value || '').trim()
    if (!keyword) return
    this._saveHistory(keyword)
    this._doSearch(keyword)
  },

  onSearchClear: function () {
    this.setData({
      searchKeyword: '',
      searchThemes: [],
      searchPhrases: [],
      searchWords: [],
      searchDone: false,
      searchFocused: true, // keep focus on clear
      searchActive: true
    })
  },

  onSearchCancel: function () {
    this.setData({
      searchKeyword: '',
      searchThemes: [],
      searchPhrases: [],
      searchWords: [],
      searchDone: false,
      searchFocused: false, // exit search mode
      searchActive: false
    })
  },

  onCategoryTap: function (e) {
    var category = e.currentTarget.dataset.category || ''
    this.setData({
      selectedCategory: category,
      page: 1,
      hasMore: true,
      rawItems: [],
      dateGroups: []
    })
    this._loadData()
    var keyword = (this.data.searchKeyword || '').trim()
    if (keyword) {
      this._doSearch(keyword)
    }
  },

  onHistoryTap: function (e) {
    var keyword = e.currentTarget.dataset.keyword
    this.setData({ searchKeyword: keyword })
    this._saveHistory(keyword)
    this._doSearch(keyword)
  },

  onClearHistory: function () {
    wx.removeStorageSync(SEARCH_HISTORY_KEY)
    this.setData({ searchHistory: [] })
  },

  onSearchResultTap: function (e) {
    var id = e.currentTarget.dataset.id
    var targetId = e.currentTarget.dataset.targetId
    var type = e.currentTarget.dataset.type
    
    // Save history if user clicks a result directly from auto-search
    var keyword = (this.data.searchKeyword || '').trim()
    if (keyword) {
      this._saveHistory(keyword)
    }

    if (id) {
      var url = '/pages/detail/detail?id=' + id
      if (targetId && type) {
        url += '&targetType=' + type + '&targetId=' + targetId
      }
      wx.navigateTo({ url: url })
    }
  },

  _doSearch: function (keyword) {
    var self = this
    self.setData({ searchDone: false })
    var params = { q: keyword }
    if (self.data.selectedCategory) {
      params.category = self.data.selectedCategory
    }
    api.get('/daily/search', params)
      .then(function (data) {
        var themes = (data.themes || []).map(function (t) {
          return {
            id: t.id,
            themeZh: t.theme_zh || t.themeZh || '',
            themeEn: t.theme_en || t.themeEn || '',
            date: t.date || '',
            contentId: t.content_id || t.contentId
          }
        })
        var phrases = (data.phrases || []).map(function (p) {
          return {
            id: p.id,
            phrase: p.phrase,
            meaning: p.meaning || '',
            theme: p.theme || '',
            date: p.date || '',
            contentId: p.content_id || p.contentId
          }
        })
        var words = (data.words || []).map(function (w) {
          return {
            id: w.id,
            word: w.word,
            meaning: w.meaning || '',
            theme: w.theme || '',
            date: w.date || '',
            contentId: w.content_id || w.contentId
          }
        })
        self.setData({
          searchThemes: themes,
          searchPhrases: phrases,
          searchWords: words,
          searchDone: true
        })
      })
      .catch(function (err) {
        console.error('[Library] Search failed:', err)
        self.setData({ searchDone: true, searchThemes: [], searchPhrases: [], searchWords: [] })
      })
  },

  _saveHistory: function (keyword) {
    var history = this.data.searchHistory.slice()
    var idx = history.indexOf(keyword)
    if (idx > -1) history.splice(idx, 1)
    history.unshift(keyword)
    if (history.length > MAX_HISTORY) history = history.slice(0, MAX_HISTORY)
    this.setData({ searchHistory: history })
    wx.setStorageSync(SEARCH_HISTORY_KEY, history)
  },

  // ========================
  // Other Events
  // ========================

  onContentTap: function (e) {
    var id = e.currentTarget.dataset.id
    if (id) {
      wx.navigateTo({ url: '/pages/detail/detail?id=' + id })
    }
  },

  onRetry: function () {
    this._loadData()
  }
})
