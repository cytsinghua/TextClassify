from __future__ import absolute_import, division, print_function, unicode_literals

import torch
from torch import nn
from torch.nn import CrossEntropyLoss, MSELoss
from torch.nn import functional as F
from pytorch_transformers.modeling_bertLSTM import BertPreTrainedModel,BertModel

class ScaledDotProductAttention(nn.Module):
    def __init__(self, attention_dropout=0.0):
        super(ScaledDotProductAttention, self).__init__()
        self.dropout = nn.Dropout(attention_dropout)
        self.softmax = nn.Softmax(dim=2)

    def forward(self, q, k, v):
        scale = q.size(-1) ** -0.5

        attention = torch.bmm(q, k.transpose(1, 2))* scale
        attention = self.softmax(attention)
        attention = self.dropout(attention)
        context = torch.bmm(attention, v)
        return context

class TripleAttention(nn.Module):
    def __init__(self,hidden_size):
        super(TripleAttention, self).__init__()
        self.hidden_size = hidden_size
        self.layer_norm = nn.LayerNorm(self.hidden_size)
        self.FeedForward2 = nn.Sequential(
            nn.Linear(self.hidden_size, self.hidden_size),
            nn.ReLU(inplace=True),
            nn.Dropout(0.1)
        )
        self.attention = ScaledDotProductAttention()

    def forward(self, history,utterance,response):
        # history 对 utt的 增强
        context_his2utt = self.attention(utterance,history,history)
        context_his2utt = self.FeedForward2(context_his2utt)
        # utt 对 his 的增强
        context_utt2his = self.attention(history,utterance,utterance)
        context_utt2his = self.FeedForward2(context_utt2his)
        # hist 对 resp的 交互
        context_his2resp = self.attention(response,history,history)
        context_his2resp = self.FeedForward2(context_his2resp)
        # resp 对 hist 的增强
        context_resp2hist = self.attention(history,response,response)
        context_resp2hist = self.FeedForward2(context_resp2hist)
        # utt 对 resp 的增强
        context_utt2resp = self.attention(utterance,response,response)
        context_utt2resp = self.FeedForward2(context_utt2resp)
        # resp 对 utt 的增强
        context_resp2utt = self.attention(response,utterance,utterance)
        context_resp2utt = self.FeedForward2(context_resp2utt)

        # 层归一化
        context_hist = self.layer_norm(context_utt2his+context_resp2hist)
        context_resp = self.layer_norm(context_utt2resp+context_his2resp)
        context_utt = self.layer_norm(context_resp2utt+context_his2utt)

        return context_hist,context_resp,context_utt

class Conv1d(nn.Module):
    def __init__(self, in_channels, out_channels, filter_sizes):
        super(Conv1d, self).__init__()
        self.convs = nn.ModuleList([
            nn.Conv1d(in_channels=in_channels,
                      out_channels=out_channels,
                      kernel_size=fs)
            for fs in filter_sizes
        ])

        self.init_params()

    def init_params(self):
        for m in self.convs:
            nn.init.xavier_uniform_(m.weight.data)
            nn.init.constant_(m.bias.data, 0.1)

    def forward(self, x):
        return [nn.functional.relu(conv(x)) for conv in self.convs]

class ResnetBlock(nn.Module):
    def __init__(self, channel_size):
        super(ResnetBlock, self).__init__()
        self.channel_size = channel_size
        self.maxpool = nn.Sequential(
            nn.ConstantPad1d(padding=(0, 1), value=0),
            nn.MaxPool1d(kernel_size=3, stride=2)
        )
        self.conv = nn.Sequential(
            nn.BatchNorm1d(num_features=self.channel_size),
            nn.ReLU(),
            nn.Conv1d(self.channel_size, self.channel_size,kernel_size=3, padding=1),
            nn.BatchNorm1d(num_features=self.channel_size),
            nn.ReLU(),
            nn.Conv1d(self.channel_size, self.channel_size,kernel_size=3, padding=1),
        )

    def forward(self, x):
        x_shortcut = self.maxpool(x)
        x = self.conv(x_shortcut)
        x = x + x_shortcut
        return x

class BertForSequenceClassification(BertPreTrainedModel):
    def __init__(self, config):
        super(BertForSequenceClassification, self).__init__(config)
        self.num_labels = config.num_labels
        self.bert = BertModel(config)
        self.dropout = nn.Dropout(config.hidden_dropout_prob)
        self.batch_size = 32
        self.hidden_size = config.hidden_size

        rnn_hidden_size = 768
        num_layers = 2
        dropout = 0.2

        self.rnn = nn.LSTM(config.hidden_size, rnn_hidden_size, num_layers, bidirectional=True, batch_first=True,
                           dropout=dropout)

        # self.classifier = nn.Linear(rnn_hidden_size * 2, config.num_labels)

        n_filters = 200
        filter_sizes = [1,2,3,4,5,6,7,8,9,10]
        self.classifier = nn.Linear(len(filter_sizes) * n_filters*3, config.num_labels)
        self.convs = Conv1d(config.hidden_size, n_filters, filter_sizes)
        # 最后的全连接层
        self.fc = nn.Sequential(
            nn.Linear(rnn_hidden_size*2,self.num_labels),
            nn.BatchNorm1d(self.num_labels),
            nn.ReLU(inplace=True),
            nn.Dropout(0.5),
            nn.Linear(self.num_labels,self.num_labels)
        )
        self.dot_product_attention = ScaledDotProductAttention()
        self.layer_norm = nn.LayerNorm(self.hidden_size)
        self.FeedForward2 = nn.Sequential(

            # nn.BatchNorm1d(num_features=self.channel_size),
            nn.Linear(self.hidden_size, self.hidden_size),
            nn.ReLU(inplace=True),
            nn.Dropout(0.1)
        )
        self.triple_attention = TripleAttention(hidden_size=self.hidden_size)

        self.apply(self.init_weights)


    def forward(self,
                input_ids, token_type_ids, attention_mask,
                utterance_mask,response_mask,history_mask,
                labels=None,position_ids=None, head_mask=None):

        flat_input_ids = input_ids.view(-1, input_ids.size(-1))
        flat_token_type_ids = token_type_ids.view(-1, token_type_ids.size(-1)) if token_type_ids is not None else None
        flat_attention_mask = attention_mask.view(-1, attention_mask.size(-1)) if attention_mask is not None else None
        flat_position_ids = position_ids.view(-1, position_ids.size(-1)) if position_ids is not None else None


        sequence_output, pooling = self.bert(
            input_ids=flat_input_ids,
            position_ids=flat_position_ids,
            token_type_ids=flat_token_type_ids,
            attention_mask=flat_attention_mask, head_mask=head_mask)
        # print(sequence_output.size())
        # print(token_type_ids.size())
        # print(utterance_mask.size())
        # print(response_mask.size())

        # print(utterance_mask.view(-1) == 1)
        history_mask = history_mask.view(-1) == 1
        utterance_mask = utterance_mask.view(-1) == 1
        response_mask = response_mask.view(-1) == 1

        history_mask_output = sequence_output.view(-1,sequence_output.size(2))[history_mask].view(sequence_output.size(0),-1,sequence_output.size(2))
        utterance_mask_output = sequence_output.view(-1, sequence_output.size(2))[utterance_mask].view(sequence_output.size(0),-1,sequence_output.size(2))
        response_mask_output = sequence_output.view(-1, sequence_output.size(2))[response_mask].view(sequence_output.size(0),-1,sequence_output.size(2))
        # print(utterance_mask_output.size())
        # print(response_mask_output.size())
        # print(history_mask_output.size())
        # exit()

        context_hist,context_resp,context_utt = self.triple_attention(
            history = history_mask_output,
            utterance = utterance_mask_output,
            response = response_mask_output
        )
        for i in range(5):
            context_hist,context_resp,context_utt = self.triple_attention(
                history = context_hist,
                utterance = context_resp,
                response = context_utt
        )


        history_conved =  self.convs(context_hist.permute(0, 2, 1))
        utterance_conved = self.convs(context_utt.permute(0, 2, 1))
        response_conved = self.convs(context_resp.permute(0, 2, 1))

        # conved 是一个列表， conved[0]: [batch_size, filter_num, *]

        history_pooled = [nn.functional.max_pool1d(conv, conv.shape[2]).squeeze(2)for conv in history_conved]
        utterance_pooled = [nn.functional.max_pool1d(conv, conv.shape[2]).squeeze(2)for conv in utterance_conved]
        response_pooled = [nn.functional.max_pool1d(conv, conv.shape[2]).squeeze(2)for conv in response_conved]

        history_cat = self.dropout(torch.cat(history_pooled, dim=1))
        utterance_cat = self.dropout(torch.cat(utterance_pooled, dim=1))
        response_cat = self.dropout(torch.cat(response_pooled, dim=1))

        # pooled 是一个列表， pooled[0]: [batch_size, filter_num]
        # print(utterance_cat.size())

        logits  = self.classifier(torch.cat([history_cat,utterance_cat,response_cat],dim = -1))


        if labels is not None:
            loss_fct = CrossEntropyLoss()
            loss = loss_fct(logits.view(-1, self.num_labels), labels.view(-1))
            return loss
        else:
            return nn.functional.softmax(logits, -1)








