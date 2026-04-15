// pages/search/search.js
const api = require('../../utils/api')
const storage = require('../../utils/storage')

var SEARCH_HISTORY_KEY = 'easyspeak_search_history'
var DEBOUNCE_DELAY = 300

Page({
  data: {
    keyword: '',
    autoFocus: true,
    hasSearched: false,
    loading: false,
    phraseResults: [],
    wordResults: [],
    searchHistory: [],
    hotTopics: ['咖啡文化', '餐厅点餐', '旅行出行', '职场英语', '日常闲聊', '运动健身']
  },

  _debounceTimer: null,

  onLoad(options) {
    // If navigated with a query param, pre-fill search
    if (options && options.q) {
      this.setData({ keyword: options.q, autoFocus: false })
      this.doSearch(options.q)
    }
    this.loadSearchHistory()
  },

  onShow() {
    this.loadSearchHistory()
  },

  onUnload() {
    // Clear debounce timer
    if (this._debounceTimer) {
      clearTimeout(this._debounceTimer)
      this._debounceTimer = null
    }
  },

  /**
   * Handle search input with debounce
   */
  onInput(e) {
    var keyword = e.detail.value.trim()
    this.setData({ keyword: keyword })

    // Clear previous timer
    if (this._debounceTimer) {
      clearTimeout(this._debounceTimer)
      this._debounceTimer = null
    }

    if (!keyword) {
      this.setData({
        hasSearched: false,
        phraseResults: [],
        wordResults: [],
        loading: false
      })
      return
    }

    // Debounce: wait 300ms before searching
    var self = this
    this._debounceTimer = setTimeout(function() {
      self.doSearch(keyword)
    }, DEBOUNCE_DELAY)
  },

  /**
   * Handle search confirm (press enter)
   */
  onConfirm(e) {
    var keyword = e.detail.value.trim()
    if (keyword) {
      // Clear debounce and search immediately
      if (this._debounceTimer) {
        clearTimeout(this._debounceTimer)
        this._debounceTimer = null
      }
      this.doSearch(keyword)
    }
  },

  /**
   * Perform the actual search
   */
  doSearch(keyword) {
    var self = this

    this.setData({
      loading: true,
      hasSearched: true
    })

    api.get('/search', { q: keyword })
      .then(function(data) {
        var phraseResults = (data.phrases || []).map(function(item) {
          return {
            id: item.id,
            phrase: item.phrase,
            theme: item.theme_zh || item.theme || '',
            date: item.date || ''
          }
        })

        var wordResults = (data.words || []).map(function(item) {
          return {
            id: item.id,
            word: item.word,
            phonetic: item.phonetic || '',
            meaning: item.meaning || '',
            theme: item.theme_zh || item.theme || '',
            date: item.date || ''
          }
        })

        self.setData({
          phraseResults: phraseResults,
          wordResults: wordResults,
          loading: false
        })

        // Save to search history
        self.saveSearchHistory(keyword)
      })
      .catch(function(err) {
        console.warn('[Search] Search failed:', err)
        self.setData({ loading: false })

        // Show error
        if (err.code === -1 || err.code === -2) {
          // Network error, try local fallback
          wx.showToast({ title: '网络异常，请重试', icon: 'none' })
        }
      })
  },

  /**
   * Clear search input and results
   */
  onClear() {
    this.setData({
      keyword: '',
      hasSearched: false,
      phraseResults: [],
      wordResults: [],
      loading: false
    })
  },

  /**
   * Cancel search — go back
   */
  onCancelSearch() {
    wx.navigateBack({
      fail: function() {
        // If no previous page, go to library
        wx.switchTab({ url: '/pages/library/library' })
      }
    })
  },

  /**
   * Tap on a search history tag
   */
  onHistoryTap(e) {
    var keyword = e.currentTarget.dataset.keyword
    this.setData({ keyword: keyword })
    this.doSearch(keyword)
  },

  /**
   * Load search history from local storage
   */
  loadSearchHistory() {
    var history = storage.get(SEARCH_HISTORY_KEY) || []
    this.setData({ searchHistory: history })
  },

  /**
   * Save keyword to search history (deduplicated, max 10)
   */
  saveSearchHistory(keyword) {
    var history = storage.get(SEARCH_HISTORY_KEY) || []

    // Remove duplicates
    history = history.filter(function(item) {
      return item !== keyword
    })

    // Add to front
    history.unshift(keyword)

    // Keep max 10 items
    if (history.length > 10) {
      history = history.slice(0, 10)
    }

    storage.set(SEARCH_HISTORY_KEY, history)
    this.setData({ searchHistory: history })
  },

  /**
   * Clear all search history
   */
  onClearHistory() {
    var self = this
    wx.showModal({
      title: '清空搜索记录',
      content: '确定要清空所有搜索记录吗？',
      success: function(res) {
        if (res.confirm) {
          storage.remove(SEARCH_HISTORY_KEY)
          self.setData({ searchHistory: [] })
          wx.showToast({ title: '已清空', icon: 'success' })
        }
      }
    })
  },

  /**
   * Navigate to phrase detail page
   */
  onPhraseTap(e) {
    var id = e.currentTarget.dataset.id
    wx.navigateTo({
      url: '/pages/phrase-detail/phrase-detail?id=' + id
    })
  },

  /**
   * Navigate to word detail or word list page
   */
  onWordTap(e) {
    var id = e.currentTarget.dataset.id
    wx.navigateTo({
      url: '/pages/word-list/word-list?wordId=' + id
    })
  }
})
