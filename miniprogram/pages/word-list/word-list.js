/**
 * EasySpeak - Word List Page (单词列表页)
 * Displays all words for a daily content item in a table/list view
 * with search, filter, compact mode toggle, and flip-card modal.
 *
 * Receives content_id via page options.
 */

const api = require('../../utils/api')
const storage = require('../../utils/storage')

Page({
  data: {
    // Route params
    contentId: null,

    // Loading / error
    loading: true,
    error: false,
    errorMsg: '',

    // Content info
    themeZh: '',
    dateDisplay: '',

    // Word list
    words: [],
    filteredWords: [],

    // Search
    searchText: '',
    isSearching: false,

    // Part of speech filter
    posFilter: '',
    posOptions: [],

    // View mode
    compactMode: false,

    // Flip card modal
    showModal: false,
    modalWord: null,

    // Expanded word index (-1 = none)
    expandedWordIndex: -1
  },

  onLoad: function (options) {
    var contentId = options.content_id || options.contentId || options.id || null

    if (!contentId) {
      this.setData({
        loading: false,
        error: true,
        errorMsg: '缺少内容ID参数'
      })
      return
    }

    this.setData({ contentId: contentId })
    this._loadContent()
  },

  onShareAppMessage: function () {
    var theme = this.data.themeZh || '英语单词'
    return {
      title: 'EasySpeak · ' + theme + ' - 单词列表',
      path: '/pages/word-list/word-list?contentId=' + this.data.contentId
    }
  },

  // ========================
  // Data Loading
  // ========================

  _loadContent: function () {
    var self = this
    var contentId = this.data.contentId
    self.setData({ loading: true, error: false })

    // Try cache first
    var cacheKey = storage.KEYS.CONTENT_CACHE_PREFIX + 'detail_' + contentId
    var cached = storage.getCache(cacheKey)

    if (cached) {
      self._processContent(cached)
      self.setData({ loading: false })
    }

    api.get('/daily/content/' + contentId)
      .then(function (data) {
        storage.setCache(cacheKey, data, storage.TTL.CONTENT_DETAIL)
        self._processContent(data)
        self.setData({ loading: false, error: false })
      })
      .catch(function (err) {
        console.error('[WordList] Fetch failed:', err)
        if (cached && self.data.words.length > 0) {
          self.setData({ loading: false })
        } else {
          self.setData({
            loading: false,
            error: true,
            errorMsg: err.message || '加载失败，请重试'
          })
        }
      })
  },

  _processContent: function (data) {
    if (!data) {
      this.setData({ error: true, errorMsg: '内容不存在' })
      return
    }

    var content = data.content || data
    var words = (content.words || []).map(function (w, index) {
      return {
        id: w.id,
        word: w.word || '',
        phonetic: w.phonetic || '',
        partOfSpeech: w.part_of_speech || '',
        meaning: w.meaning || '',
        example: w.example || '',
        sort_order: w.sort_order || index
      }
    })

    // Sort by sort_order
    words.sort(function (a, b) { return a.sort_order - b.sort_order })

    // Extract unique part-of-speech values for filter
    var posSet = {}
    words.forEach(function (w) {
      if (w.partOfSpeech) {
        posSet[w.partOfSpeech] = true
      }
    })
    var posOptions = Object.keys(posSet).sort()
    posOptions.unshift('') // Add "all" option at start

    this.setData({
      words: words,
      filteredWords: words,
      posOptions: posOptions,
      themeZh: content.theme_zh || '',
      dateDisplay: this._formatDate(content.date || ''),
      error: false
    })
  },

  _formatDate: function (dateStr) {
    if (!dateStr) return ''
    var parts = dateStr.split('-')
    return parseInt(parts[1]) + '月' + parseInt(parts[2]) + '日'
  },

  // ========================
  // Search & Filter
  // ========================

  onSearchInput: function (e) {
    var text = e.detail.value
    this.setData({ searchText: text, isSearching: text.length > 0 })
    this._applyFilters(text, this.data.posFilter)
  },

  onSearchClear: function () {
    this.setData({ searchText: '', isSearching: false })
    this._applyFilters('', this.data.posFilter)
  },

  onSearchFocus: function () {
    this.setData({ isSearching: true })
  },

  onSearchBlur: function () {
    if (!this.data.searchText) {
      this.setData({ isSearching: false })
    }
  },

  onPosFilter: function (e) {
    var pos = e.currentTarget.dataset.pos || ''
    this.setData({ posFilter: pos })
    this._applyFilters(this.data.searchText, pos)
  },

  _applyFilters: function (searchText, posFilter) {
    var self = this
    var words = self.data.words

    var filtered = words.filter(function (w) {
      // POS filter
      if (posFilter && w.partOfSpeech !== posFilter) {
        return false
      }
      // Search filter
      if (searchText) {
        var lowerSearch = searchText.toLowerCase()
        var matchWord = w.word.toLowerCase().indexOf(lowerSearch) !== -1
        var matchMeaning = w.meaning.indexOf(searchText) !== -1
        var matchPhonetic = w.phonetic.toLowerCase().indexOf(lowerSearch) !== -1
        if (!matchWord && !matchMeaning && !matchPhonetic) {
          return false
        }
      }
      return true
    })

    self.setData({
      filteredWords: filtered,
      expandedWordIndex: -1
    })
  },

  // ========================
  // View Mode
  // ========================

  onToggleCompact: function () {
    this.setData({
      compactMode: !this.data.compactMode,
      expandedWordIndex: -1
    })
  },

  // ========================
  // Word Interaction
  // ========================

  onWordTap: function (e) {
    var index = e.currentTarget.dataset.index
    var word = this.data.filteredWords[index]

    if (!word) return

    if (this.data.compactMode) {
      // In compact mode, expand inline
      if (this.data.expandedWordIndex === index) {
        this.setData({ expandedWordIndex: -1 })
      } else {
        this.setData({ expandedWordIndex: index })
      }
    } else {
      // In full mode, show flip card modal
      this.setData({
        showModal: true,
        modalWord: word
      })
    }
  },

  onModalClose: function () {
    this.setData({ showModal: false, modalWord: null })
  },

  onModalFlip: function () {
    // Toggle flip state
    var word = this.data.modalWord
    if (word) {
      word._flipped = !word._flipped
      this.setData({ modalWord: word })
    }
  },

  preventModalBubble: function () {
    // Prevent touch events from propagating through modal backdrop
  },

  onRetry: function () {
    this._loadContent()
  }
})