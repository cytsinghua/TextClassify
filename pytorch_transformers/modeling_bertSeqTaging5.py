from __future__ import absolute_import, division, print_function, unicode_literals
import torch
from torch import nn
from torch.nn import CrossEntropyLoss,BCEWithLogitsLoss
from pytorch_transformers.modeling_bertLSTM import BertPreTrainedModel,BertModel


class BertForTokenClassification(BertPreTrainedModel):

    def __init__(self, config):
        super(BertForTokenClassification, self).__init__(config)
        self.domain_num_labels = 32
        self.dependcy_num_labels = 4
        self.domainslot_labels = 26

        self.bert = BertModel(config)
        self.dropout = nn.Dropout(config.hidden_dropout_prob)
        self.tokenstart_numlabels = 2
        self.tokenend_numlabels = 2
        self.classifier_tokenstart = nn.Sequential(
            nn.Linear(config.hidden_size,config.hidden_size),
            nn.ReLU(inplace=True),
            nn.Dropout(0.5),
            nn.Linear(config.hidden_size,self.tokenstart_numlabels)
        )
        self.classifier_tokensend = nn.Sequential(
            nn.Linear(config.hidden_size,config.hidden_size),
            nn.ReLU(inplace=True),
            nn.Dropout(0.5),
            nn.Linear(config.hidden_size,self.tokenend_numlabels)
        )
        self.classifier_sentence_domainslot = nn.Sequential(
            nn.Linear(config.hidden_size, config.hidden_size),
            nn.ReLU(inplace=True),
            nn.Dropout(0.5),
            nn.Linear(config.hidden_size, self.sentence_domainslot_numlabels)
        )
        self.classifier_tokens_domainslot = nn.Sequential(
            nn.Linear(config.hidden_size, config.hidden_size),
            nn.ReLU(inplace=True),
            nn.Dropout(0.5),
            nn.Linear(config.hidden_size, self.classifier_tokens_domainslot)
        )
        self.dropout = nn.Dropout(0.2)
        self.softmax = nn.Softmax(dim=2)



        self.apply(self.init_weights)

    def forward(self, input_ids, token_type_ids=None, attention_mask=None,
                utterance_mask = None,domainslot_mask = None,
                label_tokens_start=None,label_tokens_end=None,
                label_sentence_domainslot = None,label_tokens_domainslot=None,
                position_ids=None, head_mask=None):

        flat_input_ids = input_ids.view(-1, input_ids.size(-1))
        flat_token_type_ids = token_type_ids.view(-1, token_type_ids.size(-1)) if token_type_ids is not None else None
        flat_attention_mask = attention_mask.view(-1, attention_mask.size(-1)) if attention_mask is not None else None
        flat_position_ids = position_ids.view(-1, position_ids.size(-1)) if position_ids is not None else None

        sequence_output, pooling = self.bert(
            input_ids=flat_input_ids,
            position_ids=flat_position_ids,
            token_type_ids=flat_token_type_ids,
            attention_mask=flat_attention_mask, head_mask=head_mask)
        # print(label_sentence_domainslot.size())

        sequence_output = self.dropout(sequence_output)
        # print(sequence_output.size())
        # print(label_tokens_start.size())
        # print(label_tokens_end.size())
        # print(label_sentence_domainslot.size())
        # print(label_tokens_domainslot.size())
        # print(utterance_mask.size())
        # print(domainslot_mask.size())
        # print(1)
        # exit()
        logits_tokenstart = self.classifier_tokenstart(sequence_output)
        logits_tokenend = self.classifier_tokensend(sequence_output)
        logits_sentence_domainslot = self.classifier_sentence_domainslot(pooling)
        # print(logits_tokenstart.size())
        # print(logits_tokenend.size())
        # print(logits_sentence_domainslot.size())
        utterance_mask = utterance_mask.view(-1) == 1
        domainslot_mask = domainslot_mask.view(-1) == 1
        # print(1,label_tokens_start.size())
        # print(sequence_output.view(-1, sequence_output.size(2)).size())
        utterance_mask_output = sequence_output.view(-1, sequence_output.size(2))[utterance_mask].view(
            sequence_output.size(0), -1, sequence_output.size(2))
        domainslot_mask_output = sequence_output.view(-1, sequence_output.size(2))[domainslot_mask].view(
            sequence_output.size(0), -1, sequence_output.size(2))
        # label_tokensstart_maskoutput = label_tokens_start.view(-1, label_tokens_start.size(2))[utterance_mask].view(
        #     label_tokens_start.size(0), -1, label_tokens_start.size(2))
        # print(utterance_mask_output.size())
        # print(domainslot_mask_output.size())
        scale = utterance_mask_output.size(-1) ** -0.5
        attention = torch.bmm(utterance_mask_output, domainslot_mask_output.transpose(1, 2))* scale
        attention = self.softmax(attention)
        attention = self.dropout(attention)
        # print(attention.size())


        loss_fct = CrossEntropyLoss()
        loss_domainslot_fct = BCEWithLogitsLoss()
        # Only keep active parts of the loss
        # print(logits_sentence_domainslot.size())
        # print(label_sentence_domainslot.size())
        loss_sentence_domainslot = loss_domainslot_fct(logits_sentence_domainslot.view(-1, 1), label_sentence_domainslot.view(-1, 1))
    # if attention_mask is not None:
        active_loss_tokenstart = attention_mask.view(-1) == 1
        active_logits_tokenstart = logits_tokenstart.view(-1, self.tokenstart_numlabels)[active_loss_tokenstart]
        # active_logits_tokenstart_ = active_logits_tokenstart.view(logits_tokenstart.size(0),-1,self.tokenstart_numlabels)
        # print(active_logits_tokenstart_.size())
        # print(label_tokens_start.size())
        active_labels_tokenstart = label_tokens_start.view(-1)[:active_logits_tokenstart.size(0)]
        # print(active_logits_tokenstart.size())
        # print(active_labels_tokenstart.size())
        loss_token_start = loss_fct(active_logits_tokenstart, active_labels_tokenstart)


        active_loss_tokenend = attention_mask.view(-1) == 1
        active_logits_tokenend = logits_tokenend.view(-1, self.tokenend_numlabels)[active_loss_tokenend]
        # active_logits_tokenend_ = active_logits_tokenend.view(logits_tokenstart.size(0),-1,self.tokenend_numlabels)
        # print(active_logits_tokenstart_.size())
        # print(label_tokens_start.size())
        active_labels_tokenend = label_tokens_end.view(-1)[:active_logits_tokenend.size(0)]
        # print(active_logits_tokenstart.size())
        # print(active_labels_tokenstart.size())
        loss_token_end = loss_fct(active_logits_tokenend, active_labels_tokenend)
        # else:
        #     loss_token_start = loss_fct(logits_tokenstart.view(-1, self.tokenstart_numlabels), label_tokens_start.view(-1))
        #     loss_token_end = loss_fct(logits_tokenend.view(-1, self.tokenend_numlabels), label_tokens_end.view(-1))
        loss_token_domainslot = loss_domainslot_fct(attention.view(-1), label_tokens_domainslot.view(-1))
        # exit()
        if label_tokens_start is not None:
            return loss_token_start,loss_token_end,loss_sentence_domainslot,loss_token_domainslot
        else:
            logits_tokenstart = nn.functional.softmax(active_logits_tokenstart, -1)
            logits_tokenend = nn.functional.softmax(active_logits_tokenend, -1)
            # logits_dependcy = nn.functional.softmax(logits_dependcy, -1)
            return logits_tokenstart,logits_tokenend,logits_sentence_domainslot,attention