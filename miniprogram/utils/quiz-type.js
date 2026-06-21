function getQuizTypeMeta(type) {
  var mapping = {
    phrase_meaning_choice: { label: '短语英选中', tone: 'default' },
    meaning_to_phrase_choice: { label: '短语中选英', tone: 'default' },
    phrase_reorder: { label: '短语排序', tone: 'reorder' },
    phrase_fill_input: { label: '短语语境选择', tone: 'default' },
    phrase_listening_choice: { label: '听音选义', tone: 'listen' },
    word_meaning_choice: { label: '单词英选中', tone: 'default' },
    meaning_to_word_choice: { label: '单词中选英', tone: 'default' },
    word_phonetic_choice: { label: '单词音标', tone: 'default' },
    word_context_choice: { label: '单词语境选择', tone: 'default' }
  }

  return mapping[type] || {
    label: type || '未知题型',
    tone: 'default'
  }
}

module.exports = {
  getQuizTypeMeta: getQuizTypeMeta
}
