const api = require('../../utils/api')
const storage = require('../../utils/storage')
const auth = require('../../utils/auth')
const quizType = require('../../utils/quiz-type')

function normalizeAnswer(text) {
  return (text || '').trim().toLowerCase().replace(/\s+/g, ' ')
}


Page({
  data: {
    mode: 'overview',

    loading: true,
    currentMonth: '',
    calendarData: [],
    summary: {
      forgetting_count: 0,
      consolidating_count: 0,
      mastered_count: 0,
      new_count: 0
    },
    dueCount: 0,
    todayReviewCount: 0,
    overviewLoadFailed: false,

    dueItems: [],
    quizQueue: [],
    currentIndex: 0,
    totalQuestionCount: 0,
    currentItem: {},
    reviewStage: 2,
    reviewStageLabel: '',
    quizData: null,
    selectedKey: '',
    submitted: false,
    isCorrect: false,
    correctOptionText: '',
    finalQuiz: null,
    wordSlots: [],
    availableTiles: [],
    wordSelectSubmitted: false,
    spellingSlots: [],
    keyboardLetters: [],
    spellingSubmitted: false,
    spellingCorrect: false,
    submitting: false,

    summaryResult: {
      reviewedCount: 0,
      avgMastery: '0.0',
      masteryLabel: '',
      masteryLevel: '',
      distribution: []
    },

    showDayDetail: false,
    dayDetail: {}
  },

  _masteryRatings: [],
  _reviewResults: {},
  _completedReviewKeys: {},

  onLoad() {
    this._initPage()
  },

  onShow() {
    if (this.data.mode === 'overview') {
      this._loadOverviewData()
    }
  },

  onPullDownRefresh() {
    this._loadOverviewData()
      .then(function () {
        wx.stopPullDownRefresh()
      })
      .catch(function () {
        wx.stopPullDownRefresh()
      })
  },

  _initPage() {
    var now = new Date()
    var y = now.getFullYear()
    var m = String(now.getMonth() + 1).padStart(2, '0')
    this.setData({
      currentMonth: y + '-' + m
    })
    this._loadOverviewData()
  },

  _loadOverviewData() {
    var self = this
    var parts = self.data.currentMonth.split('-')
    var params = {
      year: parseInt(parts[0], 10),
      month: parseInt(parts[1], 10)
    }

    self.setData({
      loading: true,
      overviewLoadFailed: false
    })

    return auth.ensureLogin()
      .then(function (loggedIn) {
        if (!loggedIn) {
          self.setData({
            loading: false,
            overviewLoadFailed: true
          })
          return Promise.reject(new Error('login required'))
        }

        return api.get('/review/overview', params)
      })
      .then(function (res) {
        var rawCalendar = res.calendar_dates || []
        // Handle both formats: old API returns strings, new API returns objects
        var calendarData = []
        var dateStrings = []
        for (var i = 0; i < rawCalendar.length; i++) {
          var item = rawCalendar[i]
          if (typeof item === 'string') {
            calendarData.push({ date: item, has_content: false, learned: false, reviewed: 0 })
            dateStrings.push(item)
          } else {
            calendarData.push(item)
            dateStrings.push(item.date)
          }
        }

        self.setData({
          loading: false,
          overviewLoadFailed: false,
          calendarData: calendarData,
          dueCount: res.due_count || 0,
          todayReviewCount: res.today_review_count || res.due_count || 0,
          summary: res.memory_summary || {
            forgetting_count: 0,
            consolidating_count: 0,
            mastered_count: 0,
            new_count: 0
          }
        })

        if (dateStrings.length > 0) {
          storage.set(storage.KEYS.STUDY_CALENDAR, dateStrings)
        }
      })
      .catch(function (err) {
        console.error('[Review] Failed to load overview:', err)
        self.setData({
          loading: false,
          overviewLoadFailed: true
        })
      })
  },

  onMonthChange(e) {
    var year = e.detail.year
    var month = e.detail.month
    var m = String(month).padStart(2, '0')
    this.setData({ currentMonth: year + '-' + m })
    this._loadOverviewData()
  },

  onDayTap(e) {
    var dayData = e.detail.dayData
    if (!dayData || !dayData.dateStr) return
    if (dayData.status === 'empty') return
    if (dayData.status === 'none' && !dayData.reviewed) return

    this.setData({
      showDayDetail: true,
      dayDetail: {
        dateStr: dayData.dateStr,
        hasReview: (dayData.reviewed || 0) > 0,
        hasContent: !!(dayData.themeZh || dayData.phraseCount || dayData.wordCount),
        themeZh: dayData.themeZh || '',
        phraseCount: dayData.phraseCount || 0,
        wordCount: dayData.wordCount || 0,
        firstPassRate: dayData.firstPassRate,
        avgMastery: dayData.avgMastery || 0,
        reviewed: dayData.reviewed || 0,
        reviewedCount: dayData.reviewedCount || dayData.reviewed || 0,
        reviewPhraseCount: dayData.reviewPhraseCount || 0,
        reviewWordCount: dayData.reviewWordCount || 0,
        forgotCount: dayData.forgotCount || 0,
        fuzzyCount: dayData.fuzzyCount || 0,
        rememberedCount: dayData.rememberedCount || 0,
        solidCount: dayData.solidCount || 0,
        status: dayData.status
      }
    })
  },

  closeDayDetail() {
    this.setData({ showDayDetail: false })
  },

  startReview() {
    var self = this
    if (self.data.loading) return

    wx.showLoading({ title: '加载复习内容...' })
    auth.ensureLogin()
      .then(function (loggedIn) {
        if (!loggedIn) {
          wx.hideLoading()
          return Promise.reject(new Error('login required'))
        }
        return api.get('/review/due')
      })
      .then(function (res) {
        wx.hideLoading()
        var items = res.items || []

        if (items.length === 0) {
          wx.showToast({ title: '暂无待复习内容', icon: 'none' })
          self._loadOverviewData()
          return
        }

        var queue = self._buildReviewQueue(items)
        if (queue.length === 0) {
          wx.showToast({ title: '暂无可用复习题，请稍后再试', icon: 'none' })
          self._loadOverviewData()
          return
        }
        self._masteryRatings = []
        self._reviewResults = {}
        self._completedReviewKeys = {}
        self.setData({
          mode: 'session',
          dueItems: items,
          quizQueue: queue,
          currentIndex: 0,
          totalQuestionCount: queue.length,
          submitting: false
        })
        self._loadQueueQuestion(0)
      })
      .catch(function (err) {
        wx.hideLoading()
        console.error('[Review] Failed to load due items:', err)
        wx.showToast({ title: '加载失败，请重试', icon: 'none' })
      })
  },

  _resultKey(item) {
    return item.item_type + ':' + item.id
  },

  _shuffleList(list) {
    var arr = list.slice()
    for (var i = arr.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1))
      var tmp = arr[i]
      arr[i] = arr[j]
      arr[j] = tmp
    }
    return arr
  },

  _buildReviewQueue(items) {
    var queue = []
    for (var i = 0; i < items.length; i++) {
      var item = items[i]
      var quizzes = item.review_quizzes || []
      for (var q = 0; q < quizzes.length; q++) {
        queue.push({ item: item, quiz: quizzes[q], questionIndex: q, itemQuestionCount: quizzes.length })
      }
    }
    queue = this._shuffleList(queue)

    for (var index = 1; index < queue.length; index++) {
      if (this._resultKey(queue[index].item) !== this._resultKey(queue[index - 1].item)) continue
      for (var swapIndex = index + 1; swapIndex < queue.length; swapIndex++) {
        if (this._resultKey(queue[swapIndex].item) !== this._resultKey(queue[index - 1].item)) {
          var tmp = queue[index]
          queue[index] = queue[swapIndex]
          queue[swapIndex] = tmp
          break
        }
      }
    }
    return queue
  },

  _quizTypeLabel(quiz) {
    var meta = quizType.getQuizTypeMeta((quiz || {}).question_type || '')
    return meta.label || '复习题'
  },

  _loadQueueQuestion(index) {
    var entry = this.data.quizQueue[index]
    if (!entry) {
      this._showSummary()
      return
    }
    var item = entry.item
    var quiz = entry.quiz || {}
    var interactionType = quiz.interaction_type || 'choice'
    var base = {
      currentIndex: index,
      currentItem: item,
      reviewStage: 2,
      reviewStageLabel: this._quizTypeLabel(quiz),
      selectedKey: '',
      submitted: false,
      isCorrect: false,
      correctOptionText: '',
      quizData: quiz,
      finalQuiz: null,
      finalQuizMode: '',
      finalQuizAnswer: '',
      wordSlots: [],
      availableTiles: [],
      wordSelectSubmitted: false,
      spellingSlots: [],
      keyboardLetters: [],
      spellingSubmitted: false,
      spellingCorrect: false,
      submitting: false
    }
    if (interactionType === 'choice') {
      base.quizData = quiz
      this.setData(base)
      return
    }
    base.reviewStage = 4
    base.finalQuiz = quiz
    base.finalQuizMode = interactionType
    base.finalQuizAnswer = (quiz.accepted_answers && quiz.accepted_answers[0]) || quiz.correct_phrase || quiz.answer || ''
    this.setData(base)
    this._enterInteractiveQuiz(quiz)
  },

  _markQuestionResult(correct) {
    var entry = this.data.quizQueue[this.data.currentIndex] || {}
    var item = entry.item || this.data.currentItem
    var key = this._resultKey(item)
    if (!this._reviewResults[key]) {
      this._reviewResults[key] = { total: 0, correct: 0 }
    }
    this._reviewResults[key].total += 1
    if (correct) this._reviewResults[key].correct += 1
  },

  _markStageResult(stage, correct) {
    this._markQuestionResult(correct)
  },

  onReviewSelectOption(e) {
    if (this.data.submitted) return
    this.setData({ selectedKey: e.currentTarget.dataset.key })
  },

  onReviewSubmitChoice() {
    if (this.data.submitted) return
    if (!this.data.selectedKey) {
      wx.showToast({ title: '请先选择答案', icon: 'none' })
      return
    }
    var quiz = this.data.quizData || {}
    var selectedKey = this.data.selectedKey
    var options = quiz.options || []
    var correctOption = null
    var selectedOption = null
    for (var i = 0; i < options.length; i++) {
      var isAnswer = !!options[i].is_answer || options[i].key === quiz.answer_key
      if (isAnswer) correctOption = options[i]
      if (options[i].key === selectedKey) selectedOption = options[i]
    }
    var isCorrect = !!correctOption && selectedKey === correctOption.key
    var correctText = correctOption ? correctOption.key + '. ' + correctOption.text : ((quiz.accepted_answers || [])[0] || '')
    this._markQuestionResult(isCorrect)
    this.setData({
      submitted: true,
      isCorrect: isCorrect,
      correctOptionText: correctText,
      selectedKey: selectedOption ? selectedKey : ''
    })
    wx.vibrateShort({ type: isCorrect ? 'light' : 'heavy' })
  },

  onReviewChoiceNext() {
    if (!this.data.submitted) return
    this._advanceAfterQuestion()
  },

  _enterInteractiveQuiz(quiz) {
    quiz = quiz || {}
    if (quiz.interaction_type === 'word_select' || quiz.interaction_type === 'reorder') {
      var answer = (quiz.accepted_answers && quiz.accepted_answers[0]) || quiz.correct_phrase || this.data.currentItem.text || ''
      var words = answer.split(' ').filter(Boolean)
      var slots = words.map(function () { return { text: '', isCorrect: null } })
      var tiles = (quiz.options || []).map(function (option) { return { key: option.key, text: option.text, used: false } })
      if (!tiles.length) {
        tiles = words.map(function (text, index) { return { key: String(index), text: text, used: false } })
      }
      this.setData({
        finalQuiz: quiz,
        finalQuizMode: quiz.interaction_type || quiz.type || '',
        finalQuizAnswer: answer,
        wordSlots: slots,
        availableTiles: tiles,
        wordSelectSubmitted: false,
        spellingSlots: [],
        keyboardLetters: [],
        spellingSubmitted: false,
        spellingCorrect: false
      })
      return
    }

    var spellingAnswer = (quiz.accepted_answers && quiz.accepted_answers[0]) || quiz.answer || this.data.currentItem.text || ''
    var chars = []
    for (var i = 0; i < spellingAnswer.length; i++) {
      if (/[a-zA-Z]/.test(spellingAnswer[i])) {
        chars.push({ text: '', expected: spellingAnswer[i].toLowerCase(), isCorrect: null })
      }
    }
    var letters = (quiz.letters || chars.map(function (slot) { return slot.expected })).map(function (letter) {
      return { text: letter, used: false }
    })
    this.setData({
      finalQuiz: quiz,
      finalQuizMode: quiz.interaction_type || quiz.type || '',
      finalQuizAnswer: spellingAnswer,
      wordSlots: [],
      availableTiles: [],
      wordSelectSubmitted: false,
      spellingSlots: chars,
      keyboardLetters: letters,
      spellingSubmitted: false,
      spellingCorrect: false
    })
  },

  _enterFinalQuiz() {
    this._enterInteractiveQuiz(this.data.finalQuiz || {})
  },

  onReviewWordTileTap(e) {
    if (this.data.wordSelectSubmitted) return
    var tileIndex = e.currentTarget.dataset.index
    var slots = this.data.wordSlots.slice()
    var tiles = this.data.availableTiles.slice()
    if (!tiles[tileIndex] || tiles[tileIndex].used) return
    var emptyIndex = -1
    for (var i = 0; i < slots.length; i++) {
      if (!slots[i].text) { emptyIndex = i; break }
    }
    if (emptyIndex === -1) return
    slots[emptyIndex] = { text: tiles[tileIndex].text, isCorrect: null }
    tiles[tileIndex] = { text: tiles[tileIndex].text, used: true }
    this.setData({ wordSlots: slots, availableTiles: tiles })
    if (slots.every(function (slot) { return !!slot.text })) {
      var self = this
      setTimeout(function () { self._checkReviewWordSelect() }, 250)
    }
  },

  onReviewSlotTap(e) {
    if (this.data.wordSelectSubmitted) return
    var slotIndex = e.currentTarget.dataset.index
    var slots = this.data.wordSlots.slice()
    var tiles = this.data.availableTiles.slice()
    var removedText = slots[slotIndex] && slots[slotIndex].text
    if (!removedText) return
    slots[slotIndex] = { text: '', isCorrect: null }
    for (var i = 0; i < tiles.length; i++) {
      if (tiles[i].text === removedText && tiles[i].used) {
        tiles[i] = { text: removedText, used: false }
        break
      }
    }
    this.setData({ wordSlots: slots, availableTiles: tiles })
  },

  _checkReviewWordSelect() {
    var quiz = this.data.finalQuiz || {}
    var correctAnswer = (quiz.accepted_answers && quiz.accepted_answers[0]) || quiz.correct_phrase || ''
    var correctWords = correctAnswer.split(' ')
    var userAnswer = this.data.wordSlots.map(function (slot) { return slot.text || '' }).join(' ')
    var allCorrect = normalizeAnswer(userAnswer) === normalizeAnswer(correctAnswer)
    var slots = this.data.wordSlots.map(function (slot, i) {
      var correct = (slot.text || '').toLowerCase() === (correctWords[i] || '').toLowerCase()
      return { text: slot.text, isCorrect: correct }
    })
    this._markQuestionResult(allCorrect)
    this.setData({ wordSlots: slots, wordSelectSubmitted: true })
    wx.vibrateShort({ type: allCorrect ? 'light' : 'heavy' })
  },

  onKeyboardLetterTap(e) {
    if (this.data.spellingSubmitted) return
    var index = e.currentTarget.dataset.index
    var letters = this.data.keyboardLetters.slice()
    if (!letters[index] || letters[index].used) return
    var slots = this.data.spellingSlots.slice()
    var emptyIndex = -1
    for (var i = 0; i < slots.length; i++) {
      if (!slots[i].text) { emptyIndex = i; break }
    }
    if (emptyIndex === -1) return
    slots[emptyIndex] = { text: letters[index].text, expected: slots[emptyIndex].expected, isCorrect: null, keyIndex: index }
    letters[index] = { text: letters[index].text, used: true }
    this.setData({ spellingSlots: slots, keyboardLetters: letters })
    if (slots.every(function (slot) { return !!slot.text })) {
      var self = this
      setTimeout(function () { self._checkSpellingKeyboard() }, 250)
    }
  },

  onSpellingSlotTap(e) {
    if (this.data.spellingSubmitted) return
    var slotIndex = e.currentTarget.dataset.index
    var slots = this.data.spellingSlots.slice()
    var letters = this.data.keyboardLetters.slice()
    var slot = slots[slotIndex]
    if (!slot || !slot.text) return
    if (slot.keyIndex !== undefined && letters[slot.keyIndex]) {
      letters[slot.keyIndex] = { text: letters[slot.keyIndex].text, used: false }
    }
    slots[slotIndex] = { text: '', expected: slot.expected, isCorrect: null }
    this.setData({ spellingSlots: slots, keyboardLetters: letters })
  },

  _checkSpellingKeyboard() {
    var allCorrect = true
    var slots = this.data.spellingSlots.map(function (slot) {
      var correct = (slot.text || '').toLowerCase() === (slot.expected || '').toLowerCase()
      if (!correct) allCorrect = false
      return { text: slot.text, expected: slot.expected, isCorrect: correct, keyIndex: slot.keyIndex }
    })
    this._markQuestionResult(allCorrect)
    this.setData({ spellingSlots: slots, spellingSubmitted: true, spellingCorrect: allCorrect })
    wx.vibrateShort({ type: allCorrect ? 'light' : 'heavy' })
  },

  onFinalNext() {
    var quiz = this.data.finalQuiz || {}
    var interactionType = quiz.interaction_type || quiz.type || ''
    if ((interactionType === 'word_select' || interactionType === 'reorder') && !this.data.wordSelectSubmitted) return
    if (interactionType === 'spelling_keyboard' && !this.data.spellingSubmitted) return
    this._advanceAfterQuestion()
  },

  _isItemReadyToComplete(item) {
    var key = this._resultKey(item)
    var result = this._reviewResults[key] || {}
    var expected = 0
    for (var i = 0; i < this.data.quizQueue.length; i++) {
      if (this._resultKey(this.data.quizQueue[i].item) === key) expected += 1
    }
    return expected > 0 && result.total >= expected
  },

  _advanceAfterQuestion() {
    var item = this.data.currentItem
    if (this._isItemReadyToComplete(item) && !this._completedReviewKeys[this._resultKey(item)]) {
      this._completeReviewItemThenAdvance(item)
      return
    }
    this._goNextQueueQuestion()
  },

  _goNextQueueQuestion() {
    var nextIndex = this.data.currentIndex + 1
    if (nextIndex >= this.data.quizQueue.length) {
      this._showSummary()
      return
    }
    this._loadQueueQuestion(nextIndex)
  },

  _completeReviewItemThenAdvance(item) {
    var self = this
    if (self.data.submitting) return
    var key = self._resultKey(item)
    var result = self._reviewResults[key] || {}
    var total = result.total || 0
    var correctCount = result.correct || 0
    var accuracy = total > 0 ? correctCount / total : 0
    var mastery = accuracy >= 1 ? 4 : (accuracy >= 0.7 ? 3 : (accuracy >= 0.4 ? 2 : (accuracy > 0 ? 1 : 0)))
    self.setData({ submitting: true })
    api.post('/review/complete', {
      item_id: item.id,
      item_type: item.item_type,
      mastery: mastery
    }).then(function () {
      self._completedReviewKeys[key] = true
      self._masteryRatings.push({ text: item.text, mastery: mastery })
      storage.recordStudyDay()
      self._goNextQueueQuestion()
    }).catch(function (err) {
      console.error('[Review] Failed to submit review quiz:', err)
      self.setData({ submitting: false })
      wx.showToast({ title: '提交失败，请重试', icon: 'none' })
    })
  },

  flipCard() {
    this.setData({
      isFlipped: !this.data.isFlipped
    })
  },

  selectMastery(e) {
    var self = this
    if (self.data.submitting) return

    var mastery = parseInt(e.currentTarget.dataset.mastery, 10)
    var currentItem = self.data.currentItem

    self.setData({ submitting: true })

    api.post('/review/complete', {
      item_id: currentItem.id,
      item_type: currentItem.item_type,
      mastery: mastery
    })
      .then(function () {
        self._masteryRatings.push({
          text: currentItem.text,
          mastery: mastery
        })

        storage.recordStudyDay()

        var nextIndex = self.data.currentIndex + 1
        if (nextIndex >= self.data.dueItems.length) {
          self._showSummary()
          return
        }

        self.setData({
          currentIndex: nextIndex,
          currentItem: self.data.dueItems[nextIndex],
          isFlipped: false,
          submitting: false
        })
      })
      .catch(function (err) {
        console.error('[Review] Failed to submit mastery:', err)
        self.setData({ submitting: false })
        wx.showToast({ title: '提交失败，请重试', icon: 'none' })
      })
  },

  _showSummary() {
    var ratings = this._masteryRatings
    var totalCount = ratings.length

    if (totalCount === 0) {
      this.setData({
        mode: 'summary',
        submitting: false,
        summaryResult: {
          reviewedCount: 0,
          avgMastery: '0.0',
          masteryLabel: '无数据',
          masteryLevel: 'none',
          distribution: []
        }
      })
      return
    }

    var sum = 0
    for (var i = 0; i < ratings.length; i++) {
      sum += ratings[i].mastery
    }
    var avg = sum / totalCount

    var masteryLabel = '需要复习'
    var masteryLevel = 'poor'
    if (avg >= 3.5) {
      masteryLabel = '太棒了！'
      masteryLevel = 'excellent'
    } else if (avg >= 2.5) {
      masteryLabel = '不错哦！'
      masteryLevel = 'good'
    } else if (avg >= 1.5) {
      masteryLabel = '继续加油'
      masteryLevel = 'fair'
    }

    var labels = [
      { level: 0, emoji: '😫', label: '完全忘了' },
      { level: 1, emoji: '😕', label: '有点印象' },
      { level: 2, emoji: '🤔', label: '想起来了' },
      { level: 3, emoji: '😊', label: '比较熟悉' },
      { level: 4, emoji: '🎯', label: '完全掌握' }
    ]

    var distribution = labels.map(function (entry) {
      var count = ratings.filter(function (item) {
        return item.mastery === entry.level
      }).length
      return {
        level: entry.level,
        emoji: entry.emoji,
        label: entry.label,
        count: count,
        pct: totalCount > 0 ? Math.round((count / totalCount) * 100) : 0
      }
    })

    this.setData({
      mode: 'summary',
      submitting: false,
      summaryResult: {
        reviewedCount: totalCount,
        avgMastery: avg.toFixed(1),
        masteryLabel: masteryLabel,
        masteryLevel: masteryLevel,
        distribution: distribution
      }
    })
  },

  _getCompletedReviewCount() {
    return this._masteryRatings.length
  },

  exitSession() {
    var self = this
    if (self.data.submitting) {
      wx.showToast({ title: '正在保存本题进度，请稍候', icon: 'none' })
      return
    }

    var reviewed = self._getCompletedReviewCount()
    var total = self.data.dueItems.length
    var hasUnfinishedCurrentItem = !!(self.data.currentItem && self.data.currentItem.id) &&
      !self._completedReviewKeys[self._resultKey(self.data.currentItem)]
    var content = ''

    if (reviewed > 0) {
      content = '已完成 ' + reviewed + '/' + total + ' 项，退出后会保存已完成进度，下次会从剩余待复习内容继续开始。'
      if (hasUnfinishedCurrentItem) {
        content += ' 当前这道未完成的题目不会保留。'
      }
    } else {
      content = '现在退出后，本次未完成的题目不会保留。下次进入会从待复习内容重新开始。'
    }

    wx.showModal({
      title: '退出智能复习',
      content: content,
      confirmText: '保存并退出',
      cancelText: '继续复习',
      success: function (res) {
        if (!res.confirm) return
        self.backToOverview(function () {
          if (reviewed > 0) {
            wx.showToast({ title: '进度已保存', icon: 'success' })
          } else {
            wx.showToast({ title: '已退出复习', icon: 'none' })
          }
        })
      }
    })
  },

  reviewAgain() {
    this.setData({ mode: 'overview' })
    this.startReview()
  },

  backToOverview(done) {
    this._masteryRatings = []
    this._reviewResults = {}
    this._completedReviewKeys = {}
    this.setData({
      mode: 'overview',
      dueItems: [],
      quizQueue: [],
      currentIndex: 0,
      totalQuestionCount: 0,
      currentItem: {},
      reviewStage: 2,
      reviewStageLabel: '',
      quizData: null,
      selectedKey: '',
      submitted: false,
      isCorrect: false,
      correctOptionText: '',
      finalQuiz: null,
      finalQuizMode: '',
      finalQuizAnswer: '',
      wordSlots: [],
      availableTiles: [],
      wordSelectSubmitted: false,
      spellingSlots: [],
      keyboardLetters: [],
      spellingSubmitted: false,
      spellingCorrect: false,
      isFlipped: false,
      submitting: false
    })
    this._loadOverviewData()
      .finally(function () {
        if (typeof done === 'function') {
          done()
        }
      })
  },

  goToQuiz() {
    wx.switchTab({
      url: '/pages/quiz/quiz'
    })
  },

  onShareAppMessage() {
    if (this.data.mode === 'summary') {
      var result = this.data.summaryResult
      return {
        title: '我刚刚复习了' + result.reviewedCount + '项内容，掌握度' + result.avgMastery + '！',
        path: '/pages/review/review'
      }
    }

    return {
      title: 'EasySpeak · 智能复习',
      path: '/pages/review/review'
    }
  }
})
