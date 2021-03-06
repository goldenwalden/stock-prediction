import pickle as pkl
import gzip
import numpy
import random
import math
import pandas as pd
from datetime import datetime
from datetime import timedelta
from scipy import stats
import timeit


def delay(j, day):
    return (datetime.strptime(j, '%Y-%m-%d') - timedelta(days=day)).strftime('%Y-%m-%d')


class TextIterator:
    """Simple Bitext iterator."""

    def __init__(self, source, label, technical,
                 dict, delay1=3, delay2=7, delay_tech=5, types='title',
                 batch_size=32,
                 n_words=-1,
                 cut_word=False, cut_news=False,
                 shuffle=True, shuffle_sentence=False):  # delay means how many days over the past
        self.start = pd.read_csv(source).reset_index(level=0).set_index('date')
        self.source = self.start[types].groupby(self.start.index).apply(list).apply(pd.Series).fillna(
            '')  # group together
        self.source_elmo = self.start['index'].groupby(self.start.index).apply(list).apply(pd.Series).fillna(
            '')  # group together
        self.label = pd.read_csv(label).set_index('Date')
        self.technical = pd.read_csv(technical)
        with open(dict, 'rb') as f:
            self.dict = pkl.load(f)
        self.types = types
        self.batch_size = batch_size
        self.n_words = n_words
        self.shuffle = shuffle
        self.shuffle_sentence = shuffle_sentence
        self.delay1 = delay1
        self.delay2 = delay2
        self.delay_tec = delay_tech  # delay_tec = 1 means one day ago
        self.types = types
        self.end_of_data = False
        self.cut_word = cut_word if cut_word else float('inf')  # cut the word
        self.cut_news = cut_news if cut_news else None  # cut the sentence
        self.source_buffer = []
        self.source_d1_buffer = []
        self.source_d2_buffer = []
        self.source_elmo_buffer = []
        self.source_d1_elmo_buffer = []
        self.source_d2_elmo_buffer = []
        self.label_buffer = []
        self.technical_buffer = []
        self.k = batch_size * 20
        self.index = 0

    def __iter__(self):
        return self

    def reset(self):
        # self.source.seek(0)
        # self.label.seek(0)
        self.index = 0

    def __next__(self):
        if self.end_of_data:
            self.end_of_data = False
            self.reset()
            raise StopIteration

        source = []
        source_d1 = []
        source_d2 = []
        source_raw = []
        source_d1_raw = []
        source_d2_raw = []
        label = []
        temp = []
        tempd1 = []
        tempd2 = []
        tech_final = []
        source_elmo = []
        source_d1_elmo = []
        source_d2_elmo = []
        # day = (datetime.strptime(j, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
        # fill buffer, if it's empty
        assert len(self.source_buffer) == len(self.label_buffer), 'Buffer size mismatch!'

        if len(self.source_buffer) == 0:
            for j, i in enumerate(self.label.index.values[self.index:self.index + self.k]):  # j for count i for value
                try:
                    ss_elmo, d1_elmo, d2_elmo = [], [], []
                    ss = list(filter(lambda x: self.cut_word > len(x.split()) > 0,
                                     self.source.loc[delay(i, 1)].values[:self.cut_news]))
                    d1 = list(list(filter(lambda x: self.cut_word > len(x.split()) > 0, i[:self.cut_news])) for i in
                              self.source.loc[delay(i, self.delay1):delay(i, 1 + 1)].values)
                    d2 = list(list(filter(lambda x: self.cut_word > len(x.split()) > 0, i[:self.cut_news])) for i in
                              self.source.loc[delay(i, self.delay2):delay(i, self.delay1 + 1)].values)
                    ll = self.label.loc[i].values
                    idx = self.technical.index[self.technical['Date'] == i][0]
                    ## 8 means the index of column, T is transpose
                    tec = self.technical.iloc[idx - self.delay_tec:idx, 8:].values
                    ss_elmo = list(filter(None, self.source_elmo.loc[delay(i, 1)].values[:self.cut_news]))
                    d1_elmo = list(
                        list(filter(None, i[:self.cut_news])) for i in
                        self.source_elmo.loc[delay(i, self.delay1):delay(i, 1 + 1)].values)
                    d2_elmo = list(
                        list(filter(None, i[:self.cut_news])) for i in
                        self.source_elmo.loc[delay(i, self.delay2):delay(i, self.delay1 + 1)].values)
                except KeyError as e:  # out of length
                    print(i + ' ' + str(e))
                    continue
                assert list(map(len, d1)) == list(map(len, d1_elmo)), 'Buffer size mismatch!'
                self.source_buffer.append(ss)
                self.source_d1_buffer.append(d1)
                self.source_d2_buffer.append(d2)
                self.label_buffer.append(int(ll))
                self.technical_buffer.append(tec)
                self.source_elmo_buffer.append(ss_elmo)
                self.source_d1_elmo_buffer.append(d1_elmo)
                self.source_d2_elmo_buffer.append(d2_elmo)
            if 'j' in locals():
                self.index += j + 1
            ##TODO delete useless

            if self.shuffle:
                # sort by target buffer
                tlen = numpy.array([len(t) for t in self.source_buffer])
                tidx = tlen.argsort()
                # argsort the index from low to high
                # shuffle mini-batch
                tindex = []
                ##Todo shuffle
                small_index = list(range(int(math.ceil(len(tidx) * 1. / self.batch_size))))
                random.shuffle(small_index)
                for i in small_index:
                    if (i + 1) * self.batch_size > len(tidx):
                        tindex.extend(tidx[i * self.batch_size:])
                    else:
                        tindex.extend(tidx[i * self.batch_size:(i + 1) * self.batch_size])
                tidx = tindex

                _sbuf = [self.source_buffer[i] for i in tidx]
                _d1buf = [self.source_d1_buffer[i] for i in tidx]
                _d2buf = [self.source_d2_buffer[i] for i in tidx]
                _lbuf = [self.label_buffer[i] for i in tidx]
                _tech = [self.technical_buffer[i] for i in tidx]
                _s_elmobuf = [self.source_elmo_buffer[i] for i in tidx]
                _d1_elmobuf = [self.source_d1_elmo_buffer[i] for i in tidx]
                _d2_elmobuf = [self.source_d2_elmo_buffer[i] for i in tidx]

                self.source_buffer = _sbuf
                self.source_d1_buffer = _d1buf
                self.source_d2_buffer = _d2buf
                self.label_buffer = _lbuf
                self.technical_buffer = _tech
                self.source_elmo_buffer = _s_elmobuf
                self.source_d1_elmo_buffer = _d1_elmobuf
                self.source_d2_elmo_buffer = _d2_elmobuf
                self.source_d2_elmo_buffer = _d2_elmobuf
                ##TODO delete useless
                del _sbuf, _d1buf, _d2buf, _lbuf
            for i, d1, d2 in zip(self.source_buffer, self.source_d1_buffer, self.source_d2_buffer):
                dd1, dd2 = list(), list()
                temp.append([j.strip().split() for j in i])  # split words and save to array
                for day in d1:
                    sentence = (j.strip().split() for j in day)
                    dd1.append(list(sentence))
                tempd1.append(dd1)
                for day in d2:
                    sentence = (j.strip().split() for j in day)
                    dd2.append(list(sentence))
                tempd2.append(dd2)
                # tempd2.append([j.strip().split() for day in d2 for j in day])
            self.source_buffer = temp
            self.source_d1_buffer = tempd1
            self.source_d2_buffer = tempd2

            ##TODO delete useless
            del temp, tempd1, tempd2
            ##TODO check if the contains enough day's new
            '''
            for j, i in enumerate(self.source_d1_buffer):
                if len(i) != self.delay1 - 1:
                    print(j)
            for j, i in enumerate(self.source_d2_buffer):
                if len(i) != self.delay2 - self.delay1:
                    print(j)
            '''
            ##TODO #check if it is a list
            '''
            if isinstance(self.source_buffer[0][0], list) is not True:  
                for i in self.source_buffer:
                    temp.append([j.strip().split() for j in i])
                self.source_buffer = temp
            '''
        if len(self.source_buffer) == 0 or len(self.label_buffer) == 0:
            self.end_of_data = False
            self.reset()
            raise StopIteration

        try:
            # actual work here
            '''for i in self.source_buffer:
                source_temp = []
                for j in i:  # len(source_buffer)       # read from source file and map to word index
                    j.insert(0, '_BOS_')
                    j.append('_EOS_')
                    ss = [self.dict[w] if w in self.dict else 1 for w in j]
                    if self.n_words > 0:
                        ss = [w if w < self.n_words else 1 for w in ss]
                        # read label
                    source_temp.append(ss)
                source.append(source_temp)
                label.append(self.label_buffer.pop(0))
                if len(source) >= self.batch_size or len(label) >= self.batch_size:
                    break
            del self.source_buffer[0:self.batch_size]'''  # doesn't make any freaky sense
            while True:
                # read from source file and map to word index
                source_temp, source_d1_temp, source_d2_temp = [], [], []
                try:
                    j = self.source_buffer.pop(0)  # 1 day before
                    d1j = self.source_d1_buffer.pop(0)  # delay1 day before
                    d2j = self.source_d2_buffer.pop(0)  # delay2 day before
                except IndexError:
                    break
                ##TODO do shuffle 
                if self.shuffle_sentence:
                    numpy.random.shuffle(j)
                for i in j:  # deal with 1 day before
                    # i.insert(0, '_BOS_')
                    # i.append('_EOS_')
                    ss = [self.dict[w] if w in self.dict else 1 for w in i]  # 1 means _UNK_
                    if self.n_words > 0:
                        ss = [w if w < self.n_words else 1 for w in ss]  # 1 means _UNK_
                    source_temp.append(ss)
                for a in d1j:  # deal with delay1
                    if self.shuffle_sentence:
                        numpy.random.shuffle(a)
                    _sd1 = []
                    for i in a:
                        # i.insert(0, '_BOS_')
                        # i.append('_EOS_')
                        ss = [self.dict[w] if w in self.dict else 1 for w in i]  # 1 means _UNK_
                        if self.n_words > 0:
                            ss = [w if w < self.n_words else 1 for w in ss]  # 1 means _UNK_
                        _sd1.append(ss)
                    source_d1_temp.append(_sd1)
                for a in d2j:  # deal with delay2
                    if self.shuffle_sentence:
                        numpy.random.shuffle(a)
                    _sd2 = []
                    for i in a:
                        # i.insert(0, '_BOS_')
                        # i.append('_EOS_')
                        ss = [self.dict[w] if w in self.dict else 1 for w in i]  # 1 means _UNK_
                        if self.n_words > 0:
                            ss = [w if w < self.n_words else 1 for w in ss]  # 1 means _UNK_
                        _sd2.append(ss)
                    source_d2_temp.append(_sd2)
                # read label
                '''
                ll = self.label_buffer.pop(0)
                tech_tech = self.technical_buffer.pop(0)
                s_elmo_elmo = self.source_elmo_buffer.pop(0)
                d1_elmo_elmo = self.source_d1_elmo_buffer.pop(0)
                d2_elmo_elmo = self.source_d2_elmo_buffer.pop(0)
                '''
                source.append(source_temp)
                source_d1.append(source_d1_temp)
                source_d2.append(source_d2_temp)
                source_raw.append(j)
                source_d1_raw.append(d1j)
                source_d2_raw.append(d2j)
                label.append(self.label_buffer.pop(0))
                tech_final.append(self.technical_buffer.pop(0))
                source_elmo.append(self.source_elmo_buffer.pop(0))
                source_d1_elmo.append(self.source_d1_elmo_buffer.pop(0))
                source_d2_elmo.append(self.source_d2_elmo_buffer.pop(0))
                ##TODO delete useless
                ##del source_temp, source_d1_temp, source_d2_temp

                if len(source) >= self.batch_size or len(source_d1) >= self.batch_size or len(
                        source_d2) >= self.batch_size or len(label) >= self.batch_size:
                    break
        except IOError:
            self.end_of_data = True

        if len(source) <= 0 or len(label) <= 0:
            self.end_of_data = False
            self.reset()
            raise StopIteration
        ##TODO raw string with padding
        n_samples = len(source_raw)  # number of samples== batch
        maxlen_x = numpy.max(list(map(len, source_raw)))  # max time step
        maxlen_xd1 = numpy.max([numpy.max(i) for i in list(map(lambda x: list(map(len, x)), source_d1_raw))])
        maxlen_xd2 = numpy.max([numpy.max(i) for i in list(map(lambda x: list(map(len, x)), source_d2_raw))])
        max_sequence = max(len(j) for i in source_raw for j in i)  # find the sequence max length
        max_sequence_d1 = max(len(j) for i in source_d1_raw for z in i for j in z)
        max_sequence_d2 = max(len(j) for i in source_d2_raw for z in i for j in z)
        max_word_len = max(len(j) for i in source_raw for z in i for j in z)  # find the longest word
        np_source_raw = numpy.chararray((n_samples, maxlen_x, max_sequence), itemsize=max_word_len)
        np_source_d1_raw = numpy.chararray((n_samples, len(source_d1_raw[0]), maxlen_xd1, max_sequence_d1),
                                           itemsize=max_word_len)
        np_source_d2_raw = numpy.chararray((n_samples, len(source_d2_raw[0]), maxlen_xd2, max_sequence_d2),
                                           itemsize=max_word_len)
        for index, (i, j, k) in enumerate(zip(source_raw, source_d1_raw, source_d2_raw)):  # batch size
            for idx, ss in enumerate(i):  # time step
                np_source_raw[index, idx, :len(ss)] = ss
            for jj, day in enumerate(j):
                for idx, ss in enumerate(day):
                    np_source_d1_raw[index, jj, idx, :len(ss)] = ss
            for jj, day in enumerate(k):
                for idx, ss in enumerate(day):
                    np_source_d2_raw[index, jj, idx, :len(ss)] = ss
        ##TODO source_len contains the length of the data
        source_len = list(map(lambda x: list(map(len, x)), source))
        source_d1_len = list(map(lambda x: list(map(lambda y: list(map(len, y)), x)), source_d1))
        source_d2_len = list(map(lambda x: list(map(lambda y: list(map(len, y)), x)), source_d1))
        ##TODO these are used for elmo,contains the index of every news
        np_source_elmo = numpy.full((len(source_elmo), max(len(i) for i in source_elmo)), -1)
        np_source_d1_elmo = numpy.full(
            (len(source_d1_elmo), len(source_d1_elmo[0]), max(len(j) for i in source_d1_elmo for j in i)), -1)
        np_source_d2_elmo = numpy.full(
            (len(source_d2_elmo), len(source_d2_elmo[0]), max(len(j) for i in source_d2_elmo for j in i)), -1)
        for index, (i, j, z) in enumerate(zip(source_elmo, source_d1_elmo, source_d2_elmo)):
            np_source_elmo[index, :len(i)] = i
            for day, jj in enumerate(j):
                np_source_d1_elmo[index, day, :len(jj)] = jj
            for day, zz in enumerate(z):
                np_source_d2_elmo[index, day, :len(zz)] = zz
        return source, source_d1, source_d2, label, numpy.array(
            tech_final), source_len, source_d1_len, source_d2_len, np_source_raw, np_source_d1_raw, np_soure_d2_raw, np_source_elmo.astype(
            'int64'), np_source_d1_elmo.astype('int64'), np_source_d2_elmo.astype(
            'int64')


def main():
    train = TextIterator('../ding_new_1/train.csv',
                         '../ding_new_1/train_label.csv',
                         '../ding_new_1/technical.csv',
                         dict='../ding_new_1/vocab_cased_title.pickle',
                         delay1=3,
                         delay2=7,
                         delay_tech=5,
                         types='title',
                         n_words=43920,
                         batch_size=32, cut_word=False, cut_news=70,
                         shuffle=True)  # cut word: max length of the words in sentence
    validate = TextIterator('../ding_new_1//validate.csv',
                            '../ding_new_1/validate_label.csv',
                            '../ding_new_1/technical.csv',
                            dict='../ding_new_1/vocab_cased_title.pickle',
                            delay1=3,
                            delay2=7,
                            delay_tech=1,
                            types='title',
                            n_words=43920,
                            batch_size=32, cut_word=False, cut_news=70,
                            shuffle=True)  # cut word: max length of the words in sentence
    test = TextIterator('../ding_new_1/validate.csv',
                        '../ding_new_1/validate_label.csv',
                        '../ding_new_1/technical.csv',
                        dict='../ding_new_1/vocab_cased_title.pickle',
                        delay1=3,
                        delay2=7,
                        delay_tech=1,
                        types='title',
                        n_words=43920,
                        batch_size=32, cut_word=False, cut_news=70,
                        shuffle=True)  # cut word: max length of the words in sentence
    # cut news: max news number per day
    for i, (x, xd1, xd2, y, tech, a, b, c, d, e, f, g, h, i) in enumerate(train):
        print("train", i, 'length', len(x), tech.shape, '\n')
        print(a.shape, b.shape, c.shape, d.shape, e.shape, f.shape, g.shape, h.shape, i.shape)
    for i, (x, xd1, xd2, y, tech, a, b, c, d, e, f, g, h, i) in enumerate(validate):
        print("validate", i, 'length', len(x), tech.shape, '\n')
        print(a.shape, b.shape, c.shape, d.shape, e.shape, f.shape, g.shape, h.shape, i.shape)
    for i, (x, xd1, xd2, y, tech, a, b, c, d, e, f, g, h, i) in enumerate(test):
        print("test", i, 'length', len(x), tech.shape, '\n')
        print(a.shape, b.shape, c.shape, d.shape, e.shape, f.shape, g.shape, h.shape, i.shape)



if __name__ == '__main__':
    main()
