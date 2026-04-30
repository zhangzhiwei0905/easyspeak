/**
 * EasySpeak — Immersive Learning Session (沉浸式学习会话)
 *
 * Four-stage learning flow:
 *   Stage 1: Exposure  — show card, read aloud
 *   Stage 2: Comprehension — multiple-choice meaning quiz
 *   Stage 3: Practice  — fill-in-the-blank / reverse quiz
 *   Stage 4: Mastery   — delayed recall self-assessment
 *
 * After all stages, show a learning report.
 */

var api = require('../../utils/api')
var auth = require('../../utils/auth')
var storage = require('../../utils/storage')
var navigation = require('../../utils/navigation')

var BATCH_SIZE = 5
var MIN_EXPOSURE_MS = 4000 // minimum time on exposure card

Page({
  data: {
    // --- session meta ---
    loading: true,
    loadError: false,
    errorMsg: '',
    learnType: 'phrase', // 'phrase' or 'word'
    contentId: '',
    themeZh: '',
    themeEn: '',

    // --- overall phase ---
    // 'learning' | 'stage4' | 'report'
    phase: 'learning',

    // --- stage tracking (stages 1-3) ---
    stage: 1, // current stage: 1=exposure, 2=comprehension, 3=practice
    stageLabels: { 1: '认识', 2: '理解', 3: '练习' },

    // --- items ---
    allItems: [],       // all items from API
    queue: [],          // current working queue for stages 1-3
    retryQueue: [],     // items that need retry
    currentIndex: 0,    // index into queue
    currentItem: null,  // the item being displayed

    // --- progress counters ---
    totalItems: 0,
    processedCount: 0,  // items finished so far (across all stages)

    // --- stage 1: exposure ---
    canProceed: false,  // becomes true after MIN_EXPOSURE_MS

    // --- stage 2 & 3: quiz ---
    quizData: null,     // current quiz object {question, options, answer, hint}
    selectedKey: '',
    submitted: false,
    isCorrect: false,
    correctOptionText: '',

    // --- stage 4: mastery recall ---
    stage4Items: [],    // items for final recall round
    stage4Index: 0,
    stage4Item: null,
    stage4Flipped: false,
    stage4Mode: 'self', // 'self' or 'word_select'
    // word_select state (Duolingo-style)
    wordSlots: [],       // user-filled slots [{text, isCorrect}]
    availableTiles: [],  // tiles to pick from [{text, used}]
    wordSelectSubmitted: false,

    // --- stats for report ---
    startTime: 0,
    firstPassCorrect: 0,
    retryCorrect: 0,
    masteryResults: [], // [{item_id, item_type, mastery}]

    // --- report ---
    report: null
  },

  _exposureTimer: null,
  _audioCtx: null,
  _attemptState: null,
  _correctAudio: null,
  _wrongAudio: null,

  // ================================================
  // Lifecycle
  // ================================================

  onLoad: function (options) {
    var contentId = options.content_id || options.contentId || ''
    var learnType = options.learn_type || options.learnType || 'phrase'
    var shouldResume = options.resume === '1' || options.resume === 'true'

    if (!contentId) {
      this.setData({ loading: false, loadError: true, errorMsg: '缺少内容参数' })
      return
    }

    this.setData({
      contentId: contentId,
      learnType: learnType,
      startTime: Date.now()
    })

    this._correctAudio = wx.createInnerAudioContext()
    this._correctAudio.src = '/audio/correct.wav'
    this._wrongAudio = wx.createInnerAudioContext()
    this._wrongAudio.src = '/audio/wrong.wav'

    if (shouldResume && this._restoreDraft(contentId, learnType)) {
      return
    }

    if (!shouldResume) {
      storage.removeLearnDraft(contentId, learnType)
    }
    this._createSession()
  },

  onUnload: function () {
    this._saveDraft()
    this._clearExposureTimer()
    this._destroyAudio()
    if (this._correctAudio) { try { this._correctAudio.stop(); this._correctAudio.destroy() } catch (e) {} }
    if (this._wrongAudio) { try { this._wrongAudio.stop(); this._wrongAudio.destroy() } catch (e) {} }
  },

  // ================================================
  // Session creation
  // ================================================

  _createSession: function () {
    var self = this
    self.setData({ loading: true, loadError: false })

    auth.ensureLogin().then(function () {
      return api.post('/learn/session', {
        content_id: parseInt(self.data.contentId),
        learn_type: self.data.learnType
      })
    }).then(function (data) {
      if (!data || !data.items || data.items.length === 0) {
        self.setData({ loading: false, loadError: true, errorMsg: '没有可学习的内容' })
        return
      }

      var items = data.items

      self._attemptState = {}
      items.forEach(function (entry) {
        self._attemptState[entry.id] = {
          stage2FirstCorrect: false,
          stage3FirstCorrect: false,
          stage2Attempted: false,
          stage3Attempted: false,
          enteredRetry: false,
          completed: false
        }
      })

      self.setData({
        loading: false,
        themeZh: data.theme_zh || '',
        themeEn: data.theme_en || '',
        allItems: items,
        totalItems: items.length,
        queue: items.slice(),
        currentIndex: 0,
        currentItem: items[0],
        stage: 1,
        phase: 'learning',
        canProceed: false
      }, function () {
        self._saveDraft()
      })

      self._startExposureTimer()
      self._playItemAudio(items[0])
    }).catch(function (err) {
      console.error('[LearnSession] Create session failed:', err)
      self.setData({
        loading: false,
        loadError: true,
        errorMsg: err.message || '加载失败'
      })
    })
  },

  // ================================================
  // Stage 1: Exposure
  // ================================================

  _startExposureTimer: function () {
    var self = this
    self._clearExposureTimer()
    self.setData({ canProceed: false })
    self._exposureTimer = setTimeout(function () {
      self.setData({ canProceed: true })
    }, MIN_EXPOSURE_MS)
  },

  _clearExposureTimer: function () {
    if (this._exposureTimer) {
      clearTimeout(this._exposureTimer)
      this._exposureTimer = null
    }
  },

  _cleanPhraseText: function (text) {
    // Split on " / " and take only the first part
    if (text.indexOf(' / ') !== -1) {
      text = text.split(' / ')[0]
    }
    // Remove trailing ellipsis (… or ...)
    text = text.replace(/[.…]+$/, '')
    return text.trim()
  },

  _playItemAudio: function (item) {
    if (!item) return
    var text = ''
    if (item.type === 'phrase') {
      text = this._cleanPhraseText(item.phrase || '')
    } else {
      text = item.word || ''
    }
    if (!text) return

    var self = this
    this._destroyAudio()
    var audio = wx.createInnerAudioContext()
    this._audioCtx = audio

    var youdaoUrl = 'https://dict.youdao.com/dictvoice?audio=' + encodeURIComponent(text) + '&type=2'
    var baiduUrl = 'https://fanyi.baidu.com/gettts?lan=en&text=' + encodeURIComponent(text) + '&spd=2&source=web'
    var triedFallback = false

    audio.src = youdaoUrl
    audio.play()

    audio.onEnded(function () {})
    audio.onError(function (err) {
      console.error('[LearnSession] Audio error:', err)
      if (!triedFallback) {
        triedFallback = true
        console.log('[LearnSession] Trying Baidu TTS fallback for:', text)
        self._destroyAudio()
        var audio2 = wx.createInnerAudioContext()
        self._audioCtx = audio2
        audio2.src = baiduUrl
        audio2.play()
        audio2.onError(function (err2) {
          console.error('[LearnSession] Baidu TTS fallback also failed:', err2)
          // Silently fail — no toast
        })
      }
      // Silently fail on second error
    })
  },

  _destroyAudio: function () {
    if (this._audioCtx) {
      try { this._audioCtx.stop() } catch (e) {}
      try { this._audioCtx.destroy() } catch (e) {}
      this._audioCtx = null
    }
  },

  onPlayAudio: function () {
    this._playItemAudio(this.data.currentItem)
  },

  onExposureNext: function () {
    if (!this.data.canProceed) return
    // Move to Stage 2
    var item = this.data.currentItem
    var quiz = item.stage2_quiz

    this.setData({
      stage: 2,
      quizData: quiz,
      selectedKey: '',
      submitted: false,
      isCorrect: false,
      correctOptionText: ''
    }, this._saveDraft.bind(this))
  },

  // ================================================
  // Stage 2 & 3: Quiz interaction
  // ================================================

  onSelectOption: function (e) {
    if (this.data.submitted) return
    var key = e.currentTarget.dataset.key
    this.setData({ selectedKey: key }, this._saveDraft.bind(this))
  },

  onSubmitAnswer: function () {
    if (this.data.submitted || !this.data.selectedKey) {
      if (!this.data.selectedKey) {
        wx.showToast({ title: '请先选择答案', icon: 'none' })
      }
      return
    }

    var quiz = this.data.quizData
    var selectedKey = this.data.selectedKey
    var isCorrect = (selectedKey === quiz.answer)

    // Find correct option text
    var correctOpt = null
    for (var i = 0; i < quiz.options.length; i++) {
      if (quiz.options[i].key === quiz.answer) {
        correctOpt = quiz.options[i]
        break
      }
    }

    this.setData({
      submitted: true,
      isCorrect: isCorrect,
      correctOptionText: correctOpt ? correctOpt.key + '. ' + correctOpt.text : ''
    }, this._saveDraft.bind(this))

    // Haptic feedback
    if (isCorrect) {
      wx.vibrateShort({ type: 'light' })
      if (this._correctAudio) { this._correctAudio.stop(); this._correctAudio.play() }
    } else {
      wx.vibrateShort({ type: 'heavy' })
      if (this._wrongAudio) { this._wrongAudio.stop(); this._wrongAudio.play() }
    }
  },

  onQuizNext: function () {
    if (!this.data.submitted) return

    var stage = this.data.stage
    var isCorrect = this.data.isCorrect
    var item = this.data.currentItem
    var attempts = this._attemptState || {}
    var itemState = attempts[item.id] || {
      stage2FirstCorrect: false,
      stage3FirstCorrect: false,
      stage2Attempted: false,
      stage3Attempted: false,
      enteredRetry: false,
      completed: false
    }

    if (!isCorrect) {
      // Wrong answer: add to retry queue (will be re-tested)
      var retryQueue = this.data.retryQueue.slice()
      var exists = retryQueue.some(function (entry) {
        return entry.id === item.id
      })
      if (!exists) {
        retryQueue.push(item)
      }
      this.setData({ retryQueue: retryQueue })
      itemState.enteredRetry = true
    } else {
      if (stage === 2 && !itemState.stage2Attempted) {
        itemState.stage2FirstCorrect = true
      }
      if (stage === 3 && !itemState.stage3Attempted) {
        itemState.stage3FirstCorrect = true
      }
    }

    if (stage === 2 && !itemState.stage2Attempted) {
      itemState.stage2Attempted = true
    }
    if (stage === 3 && !itemState.stage3Attempted) {
      itemState.stage3Attempted = true
    }

    this._attemptState[item.id] = itemState

    if (stage === 2) {
      // Move to Stage 3 for correct answers, or repeat Stage 2 is handled via retry
      if (isCorrect) {
        var quiz3 = item.stage3_quiz
        this.setData({
          stage: 3,
          quizData: quiz3,
          selectedKey: '',
          submitted: false,
          isCorrect: false,
          correctOptionText: ''
        }, this._saveDraft.bind(this))
      } else {
        // Wrong in stage 2: move to next item, this one goes to retry
        this._advanceToNextItem()
      }
    } else if (stage === 3) {
      // Stage 3 done (correct or wrong) — move to next item
      if (isCorrect) {
        var updates = {}
        if (!itemState.completed) {
          if (itemState.stage2FirstCorrect && itemState.stage3FirstCorrect && !itemState.enteredRetry) {
            updates.firstPassCorrect = this.data.firstPassCorrect + 1
          } else if (itemState.enteredRetry) {
            updates.retryCorrect = this.data.retryCorrect + 1
          }
        }
        itemState.completed = true
        if (Object.keys(updates).length > 0) {
        this.setData(updates, this._saveDraft.bind(this))
      }
      }
      this._advanceToNextItem()
    }
  },

  _advanceToNextItem: function () {
    var nextIndex = this.data.currentIndex + 1
    var queue = this.data.queue

    if (nextIndex >= queue.length) {
      // Check retry queue
      if (this.data.retryQueue.length > 0) {
        // Shuffle retry items and start a new round
        var retryItems = this.data.retryQueue.slice()
        this._shuffle(retryItems)
        this.setData({
          queue: retryItems,
          retryQueue: [],
          currentIndex: 0,
          currentItem: retryItems[0],
          stage: 1,
          canProceed: false,
          selectedKey: '',
          submitted: false,
          isCorrect: false,
          retryCorrect: this.data.retryCorrect  // will increment below
        }, this._saveDraft.bind(this))
        this._startExposureTimer()
        this._playItemAudio(retryItems[0])
      } else {
        // All items passed stages 1-3 → enter Stage 4
        this._enterStage4()
      }
      return
    }

    var nextItem = queue[nextIndex]
    this.setData({
      currentIndex: nextIndex,
      currentItem: nextItem,
      stage: 1,
      canProceed: false,
      selectedKey: '',
      submitted: false,
      isCorrect: false,
      correctOptionText: ''
    }, this._saveDraft.bind(this))
    this._startExposureTimer()
    this._playItemAudio(nextItem)
  },

  _shuffle: function (arr) {
    for (var i = arr.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1))
      var tmp = arr[i]
      arr[i] = arr[j]
      arr[j] = tmp
    }
  },

  // ================================================
  // Stage 4: Mastery — delayed recall
  // ================================================

  _enterStage4: function () {
    var items = this.data.allItems.slice()
    this._shuffle(items)

    // Prepare word_select data for each item that has stage4_quiz
    var stage4Data = items.map(function (item) {
      var quiz = item.stage4_quiz || null
      var mode = 'self'
      var slots = []
      var tiles = []
      if (quiz && quiz.word_tiles && quiz.word_tiles.length > 0 && item.type === 'phrase') {
        mode = 'word_select'
        // Create empty slots based on correct phrase word count
        var correctWords = (quiz.correct_phrase || '').split(' ')
        for (var i = 0; i < correctWords.length; i++) {
          slots.push({ text: '', isCorrect: null })
        }
        // Shuffle tiles for picking
        tiles = quiz.word_tiles.map(function (t) {
          return { text: t, used: false }
        })
      }
      return { mode: mode, slots: slots, tiles: tiles }
    })

    var firstData = stage4Data[0] || { mode: 'self', slots: [], tiles: [] }

    this.setData({
      phase: 'stage4',
      stage4Items: items,
      stage4Index: 0,
      stage4Item: items[0],
      stage4Flipped: false,
      stage4Mode: firstData.mode,
      wordSlots: firstData.slots,
      availableTiles: firstData.tiles,
      wordSelectSubmitted: false,
      masteryResults: []
    }, this._saveDraft.bind(this))
  },

  onFlipCard: function () {
    if (this.data.stage4Flipped) return
    this.setData({ stage4Flipped: true }, this._saveDraft.bind(this))

    // Play audio on flip
    this._playItemAudio(this.data.stage4Item)
  },

  _getStage4Mode: function (item) {
    // Phrase items use word_select if stage4_quiz available; words use self-assess
    if (item && item.type === 'phrase' && item.stage4_quiz && item.stage4_quiz.word_tiles && item.stage4_quiz.word_tiles.length > 0) {
      return 'word_select'
    }
    return 'self'
  },

  _getItemAnswerText: function (item) {
    if (!item) return ''
    return item.type === 'phrase' ? (item.phrase || '') : (item.word || '')
  },

  // ================================================
  // Stage 4: Word Select (Duolingo-style)
  // ================================================

  onWordTileTap: function (e) {
    if (this.data.wordSelectSubmitted) return
    var tileIndex = e.currentTarget.dataset.index
    var slots = this.data.wordSlots.slice()
    var tiles = this.data.availableTiles.slice()

    // Find first empty slot
    var emptySlotIndex = -1
    for (var i = 0; i < slots.length; i++) {
      if (!slots[i].text) {
        emptySlotIndex = i
        break
      }
    }
    if (emptySlotIndex === -1) return // all slots filled

    // Fill the slot and mark tile as used
    slots[emptySlotIndex] = { text: tiles[tileIndex].text, isCorrect: null }
    tiles[tileIndex] = { text: tiles[tileIndex].text, used: true }

    this.setData({
      wordSlots: slots,
      availableTiles: tiles
    })

    // Check if all slots are filled → auto-submit
    var allFilled = true
    for (var i = 0; i < slots.length; i++) {
      if (!slots[i].text) { allFilled = false; break }
    }
    if (allFilled) {
      // Small delay for visual feedback
      var self = this
      setTimeout(function () {
        self._checkWordSelect()
      }, 300)
    }
  },

  onSlotTap: function (e) {
    if (this.data.wordSelectSubmitted) return
    var slotIndex = e.currentTarget.dataset.index
    var slots = this.data.wordSlots.slice()
    var tiles = this.data.availableTiles.slice()

    if (!slots[slotIndex] || !slots[slotIndex].text) return

    // Return word from slot to available tiles
    var removedText = slots[slotIndex].text
    slots[slotIndex] = { text: '', isCorrect: null }

    // Mark the corresponding tile as available
    for (var i = 0; i < tiles.length; i++) {
      if (tiles[i].text === removedText && tiles[i].used) {
        tiles[i] = { text: removedText, used: false }
        break
      }
    }

    this.setData({
      wordSlots: slots,
      availableTiles: tiles
    })
  },

  _checkWordSelect: function () {
    var item = this.data.stage4Item
    var quiz = item.stage4_quiz || {}
    var correctWords = (quiz.correct_phrase || '').split(' ')
    var slots = this.data.wordSlots

    // Compare each slot with correct answer
    var allCorrect = true
    var checkedSlots = slots.map(function (slot, i) {
      var correct = (slot.text || '').toLowerCase() === (correctWords[i] || '').toLowerCase()
      if (!correct) allCorrect = false
      return { text: slot.text, isCorrect: correct }
    })

    this.setData({
      wordSlots: checkedSlots,
      wordSelectSubmitted: true,
      stage4Flipped: true
    }, this._saveDraft.bind(this))

    if (allCorrect) {
      wx.vibrateShort({ type: 'light' })
      this._playItemAudio(item)
      if (this._correctAudio) { this._correctAudio.stop(); this._correctAudio.play() }
    } else {
      wx.vibrateShort({ type: 'heavy' })
      if (this._wrongAudio) { this._wrongAudio.stop(); this._wrongAudio.play() }
    }
  },

  onWordSelectNext: function () {
    if (!this.data.wordSelectSubmitted) return
    // Check if all correct
    var slots = this.data.wordSlots
    var allCorrect = true
    for (var i = 0; i < slots.length; i++) {
      if (!slots[i].isCorrect) { allCorrect = false; break }
    }
    this._recordStage4Mastery(allCorrect ? 4 : 0)
  },

  _recordStage4Mastery: function (mastery) {
    var item = this.data.stage4Item

    // Record this item's mastery
    var results = this.data.masteryResults.slice()
    results.push({
      item_id: item.id,
      item_type: item.type,
      mastery: mastery
    })

    var nextIndex = this.data.stage4Index + 1

    if (nextIndex >= this.data.stage4Items.length) {
      // All done — submit and show report
      this.setData({ masteryResults: results }, this._saveDraft.bind(this))
      this._submitAndShowReport(results)
    } else {
      var nextItem = this.data.stage4Items[nextIndex]
      var nextMode = this._getStage4Mode(nextItem)
      var nextSlots = []
      var nextTiles = []

      if (nextMode === 'word_select' && nextItem.stage4_quiz) {
        var correctWords = (nextItem.stage4_quiz.correct_phrase || '').split(' ')
        for (var i = 0; i < correctWords.length; i++) {
          nextSlots.push({ text: '', isCorrect: null })
        }
        nextTiles = nextItem.stage4_quiz.word_tiles.map(function (t) {
          return { text: t, used: false }
        })
      }

      this.setData({
        masteryResults: results,
        stage4Index: nextIndex,
        stage4Item: nextItem,
        stage4Flipped: false,
        stage4Mode: nextMode,
        wordSlots: nextSlots,
        availableTiles: nextTiles,
        wordSelectSubmitted: false
      }, this._saveDraft.bind(this))
    }
  },

  onMasterySelect: function (e) {
    var mastery = parseInt(e.currentTarget.dataset.mastery)
    this._recordStage4Mastery(mastery)
  },

  // ================================================
  // Local draft persistence
  // ================================================

  _buildDraft: function () {
    if (this.data.loading || this.data.loadError || this.data.phase === 'report') return null
    if (!this.data.contentId || !this.data.learnType || this.data.allItems.length === 0) return null

    return {
      version: 1,
      savedAt: Date.now(),
      contentId: this.data.contentId,
      learnType: this.data.learnType,
      themeZh: this.data.themeZh,
      themeEn: this.data.themeEn,
      phase: this.data.phase,
      stage: this.data.stage,
      allItems: this.data.allItems,
      queue: this.data.queue,
      retryQueue: this.data.retryQueue,
      currentIndex: this.data.currentIndex,
      currentItem: this.data.currentItem,
      totalItems: this.data.totalItems,
      canProceed: this.data.canProceed,
      quizData: this.data.quizData,
      selectedKey: this.data.selectedKey,
      submitted: this.data.submitted,
      isCorrect: this.data.isCorrect,
      correctOptionText: this.data.correctOptionText,
      stage4Items: this.data.stage4Items,
      stage4Index: this.data.stage4Index,
      stage4Item: this.data.stage4Item,
      stage4Flipped: this.data.stage4Flipped,
      stage4Mode: this.data.stage4Mode,
      wordSlots: this.data.wordSlots,
      availableTiles: this.data.availableTiles,
      wordSelectSubmitted: this.data.wordSelectSubmitted,
      startTime: this.data.startTime,
      firstPassCorrect: this.data.firstPassCorrect,
      retryCorrect: this.data.retryCorrect,
      masteryResults: this.data.masteryResults,
      attemptState: this._attemptState || {}
    }
  },

  _saveDraft: function () {
    var draft = this._buildDraft()
    if (!draft) return
    storage.setLearnDraft(this.data.contentId, this.data.learnType, draft)
  },

  _clearDraft: function () {
    if (!this.data.contentId || !this.data.learnType) return
    storage.removeLearnDraft(this.data.contentId, this.data.learnType)
  },

  _restoreDraft: function (contentId, learnType) {
    var draft = storage.getLearnDraft(contentId, learnType)
    if (!draft || draft.version !== 1 || !draft.allItems || draft.allItems.length === 0) {
      return false
    }

    this._attemptState = draft.attemptState || {}
    this.setData({
      loading: false,
      loadError: false,
      errorMsg: '',
      contentId: String(contentId),
      learnType: learnType,
      themeZh: draft.themeZh || '',
      themeEn: draft.themeEn || '',
      phase: draft.phase || 'learning',
      stage: draft.stage || 1,
      allItems: draft.allItems || [],
      queue: draft.queue || [],
      retryQueue: draft.retryQueue || [],
      currentIndex: draft.currentIndex || 0,
      currentItem: draft.currentItem || null,
      totalItems: draft.totalItems || (draft.allItems || []).length,
      canProceed: !!draft.canProceed,
      quizData: draft.quizData || null,
      selectedKey: draft.selectedKey || '',
      submitted: !!draft.submitted,
      isCorrect: !!draft.isCorrect,
      correctOptionText: draft.correctOptionText || '',
      stage4Items: draft.stage4Items || [],
      stage4Index: draft.stage4Index || 0,
      stage4Item: draft.stage4Item || null,
      stage4Flipped: !!draft.stage4Flipped,
      stage4Mode: draft.stage4Mode || this._getStage4Mode(draft.stage4Item || null),
      wordSlots: draft.wordSlots || [],
      availableTiles: draft.availableTiles || [],
      wordSelectSubmitted: !!draft.wordSelectSubmitted,
      startTime: draft.startTime || Date.now(),
      firstPassCorrect: draft.firstPassCorrect || 0,
      retryCorrect: draft.retryCorrect || 0,
      masteryResults: draft.masteryResults || [],
      report: null
    })

    if (this.data.phase === 'learning' && this.data.stage === 1 && !this.data.canProceed) {
      this._startExposureTimer()
    }
    if (this.data.phase === 'learning' && this.data.currentItem) {
      this._playItemAudio(this.data.currentItem)
    }
    return true
  },

  // ================================================
  // Report submission
  // ================================================

  _submitAndShowReport: function (results) {
    var self = this
    var durationSeconds = Math.round((Date.now() - self.data.startTime) / 1000)

    // Calculate mastery distribution
    var dist = { forgot: 0, fuzzy: 0, remembered: 0, solid: 0 }
    for (var i = 0; i < results.length; i++) {
      var m = results[i].mastery
      if (m <= 0) dist.forgot++
      else if (m <= 1) dist.fuzzy++
      else if (m <= 3) dist.remembered++
      else dist.solid++
    }

    var totalItems = self.data.totalItems
    var firstPassCorrect = self.data.firstPassCorrect
    var retryCorrect = self.data.retryCorrect

    var report = {
      totalItems: totalItems,
      firstPassCorrect: firstPassCorrect,
      retryCorrect: retryCorrect,
      durationSeconds: durationSeconds,
      durationDisplay: self._formatDuration(durationSeconds),
      distribution: dist,
      firstPassRate: totalItems > 0
        ? Math.round((firstPassCorrect / totalItems) * 100)
        : 0,
      finalPassRate: totalItems > 0
        ? Math.round(((firstPassCorrect + retryCorrect) / totalItems) * 100)
        : 0
    }

    self.setData({
      phase: 'report',
      report: report
    })
    self._clearDraft()

    // Submit progress to backend (async, don't block UI)
    api.post('/learn/progress', {
      content_id: parseInt(self.data.contentId),
      learn_type: self.data.learnType,
      items: results
    }).catch(function (err) {
      console.warn('[LearnSession] Failed to submit progress:', err)
    })

    // Submit report
    api.post('/learn/report', {
      content_id: parseInt(self.data.contentId),
      learn_type: self.data.learnType,
      total_items: report.totalItems,
      first_pass_correct: report.firstPassCorrect,
      retry_correct: report.retryCorrect,
      duration_seconds: durationSeconds,
      mastery_distribution: dist
    }).then(function (res) {
      // Update streak display
      if (res && res.study_streak) {
        self.setData({
          'report.studyStreak': res.study_streak
        })
      }
      storage.recordStudyDay()
    }).catch(function (err) {
      console.warn('[LearnSession] Failed to submit report:', err)
      storage.recordStudyDay()
    })
  },

  _formatDuration: function (seconds) {
    var mins = Math.floor(seconds / 60)
    var secs = seconds % 60
    return mins + ' 分 ' + secs + ' 秒'
  },

  // ================================================
  // Navigation
  // ================================================

  onExit: function () {
    var self = this
    if (self.data.phase === 'report') {
      navigation.safeNavigateBack({
        fallbackUrl: '/pages/index/index',
        fallbackIsTab: true
      })
      return
    }

    wx.showModal({
      title: '确认退出',
      content: '学习进度将不会保存，确定退出吗？',
      confirmText: '退出',
      cancelText: '继续学习',
      success: function (res) {
        if (res.confirm) {
          navigation.safeNavigateBack({
            fallbackUrl: '/pages/index/index',
            fallbackIsTab: true
          })
        }
      }
    })
  },

  onBackToHome: function () {
    navigation.safeNavigateBack({
      fallbackUrl: '/pages/index/index',
      fallbackIsTab: true
    })
  },

  onRetry: function () {
    this._clearDraft()
    this._createSession()
  },

  onShareResult: function () {
    // Handled by onShareAppMessage
  },

  onShareAppMessage: function () {
    var report = this.data.report
    if (report) {
      return {
        title: '我刚学了' + report.totalItems + '个' + (this.data.learnType === 'phrase' ? '短语' : '单词') + '，一次通过率' + report.firstPassRate + '%！',
        path: '/pages/index/index'
      }
    }
    return {
      title: 'EasySpeak · 沉浸式英语学习',
      path: '/pages/index/index'
    }
  }
})
