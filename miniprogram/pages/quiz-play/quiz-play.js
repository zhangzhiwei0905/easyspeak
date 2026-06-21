var api = require('../../utils/api')
var auth = require('../../utils/auth')
var navigation = require('../../utils/navigation')
var quizType = require('../../utils/quiz-type')

var LIGHTNING_SECONDS = 180
var TIMER_INTERVAL = 1000
var PREPARE_PROGRESS_INTERVAL = 260

function normalizeAnswer(text) {
  return (text || '').trim().toLowerCase().replace(/\s+/g, ' ')
}

function buildReorderOptions(options, selectedKeys) {
  selectedKeys = selectedKeys || []
  return (options || []).map(function (item) {
    return Object.assign({}, item, {
      disabled: selectedKeys.indexOf(item.key) !== -1
    })
  })
}

Page({
  data: {
    loading: true,
    loadError: false,
    errorMsg: '',
    prepareProgress: 0,
    prepareText: '正在连接题库...',

    mode: 'random',
    questionCount: 10,
    quizMode: 'normal',
    contentIds: '',
    category: '',

    questions: [],
    currentIndex: 0,
    totalQuestions: 0,

    question: null,
    questionType: '',
    questionTypeLabel: '',
    questionTypeTone: 'default',
    interactionType: 'choice',
    prompt: '',
    placeholder: '',

    options: [],
    selectedKey: '',
    inputAnswer: '',
    selectedWordText: '',
    reorderSelected: [],
    reorderWords: [],
    reorderOptions: [],
    canSubmit: false,
    submitted: false,
    isCorrect: false,
    correctOptionText: '',

    isTimed: false,
    timeRemaining: LIGHTNING_SECONDS,
    timerDisplay: '03:00',
    timerWarning: false,

    results: [],
    correctCount: 0
  },

  _timer: null,
  _prepareTimer: null,
  _correctAudio: null,
  _wrongAudio: null,
  _audioCtx: null,

  onLoad: function (options) {
    var mode = options.mode || 'random'
    var questionCount = parseInt(options.questionCount, 10) || 10
    var quizMode = options.quizMode || 'normal'
    var contentIds = options.contentIds || ''
    var category = options.category || ''
    if (category) {
      try {
        category = decodeURIComponent(category)
      } catch (e) {}
    }

    this.setData({
      mode: mode,
      questionCount: questionCount,
      quizMode: quizMode,
      contentIds: contentIds,
      category: category,
      isTimed: quizMode === 'timed',
      timeRemaining: quizMode === 'timed' ? LIGHTNING_SECONDS : 0
    })

    this._correctAudio = wx.createInnerAudioContext()
    this._correctAudio.src = '/audio/correct.wav'
    this._wrongAudio = wx.createInnerAudioContext()
    this._wrongAudio.src = '/audio/wrong.wav'

    this._generateQuiz()
  },

  onUnload: function () {
    this._clearTimer()
    this._clearPrepareProgress()
    this._destroyAudio()
    if (this._correctAudio) { try { this._correctAudio.stop(); this._correctAudio.destroy() } catch (e) {} }
    if (this._wrongAudio) { try { this._wrongAudio.stop(); this._wrongAudio.destroy() } catch (e) {} }
  },

  onHide: function () {
    this._clearTimer()
  },

  onShow: function () {
    if (this.data.isTimed && this.data.questions.length > 0 && !this.data.submitted && this.data.currentIndex < this.data.totalQuestions) {
      this._startTimer()
    }
  },

  _generateQuiz: function () {
    var self = this
    self.setData({
      loading: true,
      loadError: false,
      prepareProgress: 0,
      prepareText: self.data.quizMode === 'timed' ? '正在准备闪电测验...' : '正在准备题目...'
    })
    self._startPrepareProgress()

    var body = {
      mode: self.data.mode,
      question_count: self.data.questionCount
    }

    if (self.data.contentIds) {
      body.content_ids = self.data.contentIds.split(',').map(function (item) {
        return parseInt(item, 10)
      }).filter(Boolean)
    }

    if (self.data.category) {
      body.category = self.data.category.split(',')
    }

    auth.ensureLogin().then(function (loggedIn) {
      if (!loggedIn) {
        self.setData({ loading: false, loadError: true, errorMsg: '请先登录' })
        return
      }
      return api.post('/quiz/generate', body)
    }).then(function (data) {
      if (!data || !Array.isArray(data) || data.length === 0) {
        self._clearPrepareProgress()
        self.setData({ loading: false, loadError: true, errorMsg: '没有可用的题目' })
        return
      }

      var questions = self._processQuestions(data)
      var firstQuestion = questions[0]
      var firstMeta = quizType.getQuizTypeMeta(firstQuestion.questionType)

      self._finishPrepareProgress(function () {
        self.setData({
          loading: false,
          questions: questions,
          totalQuestions: questions.length,
          currentIndex: 0,
          question: firstQuestion,
          questionType: firstQuestion.questionType,
          questionTypeLabel: firstMeta.label,
          questionTypeTone: firstMeta.tone,
          interactionType: firstQuestion.interactionType,
          prompt: firstQuestion.prompt,
          placeholder: firstQuestion.placeholder || '',
          options: firstQuestion.options,
          reorderOptions: buildReorderOptions(firstQuestion.options, []),
          canSubmit: false,
          reorderSelected: [],
          showExplanation: false
        })

        if (firstQuestion.interactionType === 'listening_choice' && firstQuestion.ttsText) {
          self._playTTS(firstQuestion.ttsText)
        }
        if (self.data.isTimed) {
          self._startTimer()
        }
      })
    }).catch(function (err) {
      console.error('[QuizPlay] Generate failed:', err)
      self._clearPrepareProgress()
      self.setData({
        loading: false,
        loadError: true,
        errorMsg: err.message || '生成题目失败'
      })
    })
  },

  _startPrepareProgress: function () {
    var self = this
    self._clearPrepareProgress()
    self._prepareTimer = setInterval(function () {
      var current = self.data.prepareProgress || 0
      if (current >= 92) return

      var next = current + (current < 35 ? 11 : current < 70 ? 7 : 3)
      if (next > 92) next = 92

      var text = '正在生成题目...'
      if (next >= 35 && next < 70) {
        text = '正在筛选合适题型...'
      } else if (next >= 70) {
        text = '正在整理答案选项...'
      }

      self.setData({
        prepareProgress: next,
        prepareText: text
      })
    }, PREPARE_PROGRESS_INTERVAL)
  },

  _clearPrepareProgress: function () {
    if (this._prepareTimer) {
      clearInterval(this._prepareTimer)
      this._prepareTimer = null
    }
  },

  _finishPrepareProgress: function (done) {
    this._clearPrepareProgress()
    this.setData({
      prepareProgress: 100,
      prepareText: '题目准备完成'
    })
    setTimeout(function () {
      if (typeof done === 'function') done()
    }, 180)
  },

  _processQuestions: function (rawQuestions) {
    return rawQuestions.map(function (item) {
      var prompt = item.prompt || ''
      var interactionType = item.interaction_type || 'choice'
      return {
        id: item.question_id,
        questionType: item.question_type || '',
        interactionType: interactionType,
        prompt: prompt,
        placeholder: item.placeholder || '',
        options: (item.options || []).map(function (opt) {
          return {
            key: opt.key,
            text: opt.text,
            isAnswer: !!opt.is_answer
          }
        }),
        acceptedAnswers: item.accepted_answers || [],
        hint: item.hint || '',
        itemType: item.item_type || '',
        ttsText: item.tts_text || '',
        explanation: item.explanation || ''
      }
    })
  },

  _startTimer: function () {
    var self = this
    self._clearTimer()
    self._timer = setInterval(function () {
      var remaining = self.data.timeRemaining - 1
      if (remaining <= 0) {
        remaining = 0
        self._clearTimer()
        self._onTimeUp()
      }

      var mins = Math.floor(remaining / 60)
      var secs = remaining % 60
      self.setData({
        timeRemaining: remaining,
        timerDisplay: String(mins).padStart(2, '0') + ':' + String(secs).padStart(2, '0'),
        timerWarning: remaining <= 30
      })
    }, TIMER_INTERVAL)
  },

  _clearTimer: function () {
    if (this._timer) {
      clearInterval(this._timer)
      this._timer = null
    }
  },

  _onTimeUp: function () {
    var self = this
    wx.showModal({
      title: '时间到！',
      content: '闪电测验时间已结束',
      showCancel: false,
      success: function () {
        self._finishQuiz()
      }
    })
  },

  onSelectOption: function (e) {
    if (this.data.submitted) return
    var key = (e.detail && e.detail.key) || (e.currentTarget && e.currentTarget.dataset && e.currentTarget.dataset.key) || ''
    if (!key) return

    if (this.data.interactionType === 'reorder') {
      var selected = this.data.reorderSelected.slice()
      if (selected.indexOf(key) !== -1) return
      selected.push(key)
      var selectedWords = selected.map(function (k) {
        var opt = this.data.options.find(function (item) { return item.key === k })
        return opt ? opt.text : ''
      }.bind(this))
      this.setData({
        reorderSelected: selected,
        reorderWords: selectedWords,
        reorderOptions: buildReorderOptions(this.data.options, selected),
        canSubmit: selected.length === this.data.options.length
      })
      return
    }

    var updates = {
      selectedKey: key,
      canSubmit: true
    }
    // For word_select, also record the selected word text
    if (this.data.interactionType === 'word_select') {
      var selectedOpt = this.data.options.find(function (item) { return item.key === key })
      updates.selectedWordText = selectedOpt ? selectedOpt.text : ''
    }
    this.setData(updates)
  },

  onInputAnswer: function (e) {
    if (this.data.submitted) return
    var inputAnswer = e.detail.value || ''
    this.setData({
      inputAnswer: inputAnswer,
      canSubmit: !!inputAnswer.trim()
    })
  },

  onSubmitAnswer: function () {
    if (this.data.submitted) return

    var question = this.data.question
    var interactionType = this.data.interactionType
    var selectedKey = this.data.selectedKey
    var inputAnswer = this.data.inputAnswer

    if ((interactionType === 'choice' || interactionType === 'listening_choice') && !selectedKey) {
      wx.showToast({ title: '请先选择答案', icon: 'none' })
      return
    }

    if (interactionType === 'word_select' && !selectedKey) {
      wx.showToast({ title: '请先选择答案', icon: 'none' })
      return
    }

    if (interactionType === 'text_input' && !inputAnswer.trim()) {
      wx.showToast({ title: '请先输入答案', icon: 'none' })
      return
    }

    if (interactionType === 'reorder') {
      var reorderSelected = this.data.reorderSelected
      if (reorderSelected.length !== this.data.options.length) {
        wx.showToast({ title: '请排列所有单词', icon: 'none' })
        return
      }
    }

    var correctAnswerText = ''
    var userAnswerText = ''
    var isCorrect = false

    if (interactionType === 'choice' || interactionType === 'listening_choice') {
      var selectedOption = this.data.options.find(function (item) { return item.key === selectedKey })
      var correctOption = this.data.options.find(function (item) { return item.isAnswer })
      userAnswerText = selectedOption ? selectedOption.text : ''
      correctAnswerText = correctOption ? correctOption.text : ''
      isCorrect = !!correctOption && correctOption.key === selectedKey
      correctAnswerText = correctOption ? correctOption.key + '. ' + correctOption.text : ''
    } else if (interactionType === 'reorder') {
      var selected = this.data.reorderSelected
      var options = this.data.options
      var userPhrase = selected.map(function (k) {
        var opt = options.find(function (item) { return item.key === k })
        return opt ? opt.text : ''
      }).join(' ')
      userAnswerText = userPhrase
      correctAnswerText = question.acceptedAnswers[0] || ''
      isCorrect = normalizeAnswer(userPhrase) === normalizeAnswer(correctAnswerText)
    } else if (interactionType === 'word_select') {
      // Same logic as choice
      var selectedOption = this.data.options.find(function (item) { return item.key === selectedKey })
      var correctOption = this.data.options.find(function (item) { return item.isAnswer })
      userAnswerText = selectedOption ? selectedOption.text : ''
      correctAnswerText = correctOption ? correctOption.text : ''
      isCorrect = !!correctOption && correctOption.key === selectedKey
      correctAnswerText = correctOption ? correctOption.text : ''
    } else {
      userAnswerText = inputAnswer.trim()
      correctAnswerText = question.acceptedAnswers[0] || ''
      isCorrect = question.acceptedAnswers.some(function (answer) {
        return normalizeAnswer(answer) === normalizeAnswer(userAnswerText)
      })
    }

    var result = {
      question: this.data.prompt,
      type: this.data.questionType,
      interactionType: interactionType,
      options: this.data.options.map(function (item) {
        return {
          key: item.key,
          text: item.text,
          isCorrect: item.isAnswer
        }
      }),
      correctAnswer: correctAnswerText,
      userAnswer: (interactionType === 'choice' || interactionType === 'listening_choice')
        ? selectedKey + '. ' + userAnswerText
        : userAnswerText,
      userAnswerKey: selectedKey,
      isCorrect: isCorrect,
      hint: question.hint || '',
      explanation: question.explanation || ''
    }

    this.setData({
      submitted: true,
      isCorrect: isCorrect,
      canSubmit: false,
      correctOptionText: correctAnswerText,
      results: this.data.results.concat([result]),
      correctCount: this.data.correctCount + (isCorrect ? 1 : 0)
    })

    // Sound effect + haptic feedback
    if (isCorrect) {
      if (this._correctAudio) { this._correctAudio.stop(); this._correctAudio.play() }
      wx.vibrateShort({ type: 'light' })
    } else {
      if (this._wrongAudio) { this._wrongAudio.stop(); this._wrongAudio.play() }
      wx.vibrateShort({ type: 'heavy' })
    }

    api.post('/quiz/submit', {
      answers: [{
        question_id: question.id,
        question_type: this.data.questionType,
        answer: userAnswerText
      }]
    }).catch(function (err) {
      console.warn('[QuizPlay] Submit answer failed:', err)
    })
  },

  onNextQuestion: function () {
    if (!this.data.submitted) return

    var nextIndex = this.data.currentIndex + 1
    if (nextIndex >= this.data.totalQuestions) {
      this._clearTimer()
      this._finishQuiz()
      return
    }

    var nextQuestion = this.data.questions[nextIndex]
    var nextMeta = quizType.getQuizTypeMeta(nextQuestion.questionType)
    this.setData({
      currentIndex: nextIndex,
      question: nextQuestion,
      questionType: nextQuestion.questionType,
      questionTypeLabel: nextMeta.label,
      questionTypeTone: nextMeta.tone,
      interactionType: nextQuestion.interactionType,
      prompt: nextQuestion.prompt,
      placeholder: nextQuestion.placeholder || '',
      options: nextQuestion.options,
      reorderOptions: buildReorderOptions(nextQuestion.options, []),
      selectedKey: '',
      inputAnswer: '',
      selectedWordText: '',
      canSubmit: false,
      submitted: false,
      isCorrect: false,
      correctOptionText: '',
      reorderSelected: [],
      reorderWords: [],
      showExplanation: false
    })

    if (nextQuestion.interactionType === 'listening_choice' && nextQuestion.ttsText) {
      this._playTTS(nextQuestion.ttsText)
    }
  },

  _finishQuiz: function () {
    var results = this.data.results.slice()
    var totalQuestions = this.data.totalQuestions

    if (results.length < totalQuestions) {
      for (var i = results.length; i < totalQuestions; i++) {
        var question = this.data.questions[i]
        var correctOption = question.options.find(function (item) { return item.isAnswer })
        results.push({
          question: question.prompt,
          type: question.questionType,
          interactionType: question.interactionType,
          options: question.options.map(function (item) {
            return {
              key: item.key,
              text: item.text,
              isCorrect: item.isAnswer
            }
          }),
          correctAnswer: (question.interactionType === 'choice' || question.interactionType === 'listening_choice')
            ? (correctOption ? correctOption.key + '. ' + correctOption.text : '')
            : (question.acceptedAnswers[0] || ''),
          userAnswer: '未作答',
          userAnswerKey: '',
          isCorrect: false,
          hint: question.hint || '',
          explanation: question.explanation || ''
        })
      }
    }

    var app = getApp()
    app.globalData.quizResult = {
      correct: this.data.correctCount,
      total: totalQuestions,
      results: results,
      mode: this.data.mode,
      questionCount: this.data.questionCount,
      quizMode: this.data.quizMode,
      contentIds: this.data.contentIds
    }

    wx.redirectTo({
      url: '/pages/quiz-result/quiz-result'
    })
  },

  onReplayAudio: function () {
    var question = this.data.question
    if (question && question.ttsText) {
      this._playTTS(question.ttsText)
    }
  },

  onUndoReorder: function () {
    if (this.data.submitted) return
    var selected = this.data.reorderSelected.slice()
    if (selected.length === 0) return
    selected.pop()
    var selectedWords = selected.map(function (k) {
      var opt = this.data.options.find(function (item) { return item.key === k })
      return opt ? opt.text : ''
    }.bind(this))
    this.setData({
      reorderSelected: selected,
      reorderWords: selectedWords,
      reorderOptions: buildReorderOptions(this.data.options, selected),
      canSubmit: false
    })
  },

  onRemoveReorderWord: function (e) {
    if (this.data.submitted) return
    var removeIndex = e.currentTarget.dataset.index
    var selected = this.data.reorderSelected.slice()
    if (removeIndex < 0 || removeIndex >= selected.length) return
    selected.splice(removeIndex, 1)
    var selectedWords = selected.map(function (k) {
      var opt = this.data.options.find(function (item) { return item.key === k })
      return opt ? opt.text : ''
    }.bind(this))
    this.setData({
      reorderSelected: selected,
      reorderWords: selectedWords,
      reorderOptions: buildReorderOptions(this.data.options, selected),
      canSubmit: false
    })
  },

  onToggleExplanation: function () {
    this.setData({
      showExplanation: !this.data.showExplanation
    })
  },

  _playTTS: function (text) {
    if (!text) return
    this._destroyAudio()
    var audio = wx.createInnerAudioContext()
    this._audioCtx = audio

    var youdaoUrl = 'https://dict.youdao.com/dictvoice?audio=' + encodeURIComponent(text) + '&type=2'
    var baiduUrl = 'https://fanyi.baidu.com/gettts?lan=en&text=' + encodeURIComponent(text) + '&spd=2&source=web'
    var self = this
    var triedFallback = false

    audio.src = youdaoUrl
    audio.play()

    audio.onError(function () {
      if (!triedFallback) {
        triedFallback = true
        self._destroyAudio()
        var audio2 = wx.createInnerAudioContext()
        self._audioCtx = audio2
        audio2.src = baiduUrl
        audio2.play()
        audio2.onError(function () {})
      }
    })
  },

  _destroyAudio: function () {
    if (this._audioCtx) {
      try { this._audioCtx.stop() } catch (e) {}
      try { this._audioCtx.destroy() } catch (e) {}
      this._audioCtx = null
    }
  },

  onRetry: function () {
    this._generateQuiz()
  },

  onBack: function () {
    navigation.safeNavigateBack({
      fallbackUrl: '/pages/quiz/quiz',
      fallbackIsTab: true
    })
  }
})
