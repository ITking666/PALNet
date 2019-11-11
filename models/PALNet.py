#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import math
import torch
import torch.nn as nn
from torch.nn import functional as F
from torch.autograd import Variable
# from torch.nn.parameter import Parameter


# ----------------------------------------------------------------------
from torch_scatter import scatter_max
class Project2Dto3D(nn.Module):
    def __init__(self, w=240, h=144, d=240):
        super(Project2Dto3D, self).__init__()
        self.w = w
        self.h = h
        self.d = d

    def forward(self, x2d, idx):
        # bs, c, img_h, img_w = x2d.shape
        bs, c, _, _ = x2d.shape
        src = x2d.view(bs, c, -1)
        idx = idx.view(bs, 1, -1)
        index = idx.expand(-1, c, -1)  # expand to c channels

        x3d = x2d.new_zeros((bs, c, self.w*self.h*self.d))
        x3d, _ = scatter_max(src, index, out=x3d)  # dim_size=240*144*240,

        x3d = x3d.view(bs, c, self.w, self.h, self.d)  # (BS, c, vW, vH, vD)
        x3d = x3d.permute(0, 1, 4, 3, 2)     # (BS, c, vW, vH, vD)--> (BS, c, vD, vH, vW)
        return x3d


# takes as inputs the depth and fTSDF
class SSC_PALNet(nn.Module):
    def __init__(self):
        super(SSC_PALNet, self).__init__()

        # ---- depth
        depth_out = 6
        self.conv2d_depth = nn.Sequential(
            nn.Conv2d(1, depth_out, 3, 1, 1),
            nn.ReLU(inplace=True),
            # nn.InstanceNorm2d(depth_out),
        )
        in_ch = depth_out / 2

        self.res_depth = nn.Sequential(
            nn.Conv2d(depth_out, in_ch, 1, 1, 0),
            nn.ReLU(inplace=True),
            nn.Conv2d(in_ch, in_ch, 3, 1, 1),
            nn.ReLU(inplace=True),
            nn.Conv2d(in_ch, depth_out, 1, 1, 0),
        )

        self.project_layer = Project2Dto3D(240, 144, 240)  # w=240, h=144, d=240

        in_channel_3d = depth_out
        stride = 2
        self.pool1 = nn.Conv3d(in_channel_3d, 8, 7, stride, 3)
        self.reduction2_1 = nn.Conv3d(8, 16, 1, 1, 0, bias=False)
        self.conv2_1 = nn.Sequential(
            nn.Conv3d(8, 8, 1, 1, 0),
            nn.ReLU(inplace=True),
            nn.Conv3d(8, 8, 3, 1, 1),
            nn.ReLU(inplace=True),
            nn.Conv3d(8, 16, 1, 1, 0)
        )

        # ---- tsdf
        # depth_tsdf = 1
        in_channel_3d = 1
        stride = 2
        self.pool2 = nn.Conv3d(in_channel_3d, 8, 7, stride, 3)
        self.reduction2_2 = nn.Conv3d(8, 16, 1, 1, 0, bias=False)
        self.conv2_2 = nn.Sequential(
            nn.Conv3d(8, 8, 1, 1, 0),
            nn.ReLU(inplace=True),
            nn.Conv3d(8, 8, 3, 1, 1),
            nn.ReLU(inplace=True),
            nn.Conv3d(8, 16, 1, 1, 0)
        )

        # stride = 2
        # self.pool2 = nn.MaxPool3d(kernel_size=2, stride=2)
        # self.pool2 = nn.Conv3d(32, 32, 3, stride, 1)

        # stride = 1
        stride = 2
        self.reduction3_1 = nn.Conv3d(16, 32, 1, stride, 0, bias=False)
        self.conv3_1 = nn.Sequential(
            nn.Conv3d(16, 8, 1, stride, 0),
            nn.ReLU(inplace=True),
            nn.Conv3d(8, 8, 3, 1, 1),
            nn.ReLU(inplace=True),
            nn.Conv3d(8, 32, 1, 1, 0),
        )

        stride = 2
        self.reduction3_2 = nn.Conv3d(16, 32, 1, stride, 0, bias=False)
        self.conv3_2 = nn.Sequential(
            nn.Conv3d(16, 8, 1, stride, 0),
            nn.ReLU(inplace=True),
            nn.Conv3d(8, 8, 3, 1, 1),
            nn.ReLU(inplace=True),
            nn.Conv3d(8, 32, 1, 1, 0),
        )

        # -------------1/4

        self.conv3_3 = nn.Sequential(
            nn.Conv3d(64, 32, 1, 1, 0),
            nn.ReLU(inplace=True),
            nn.Conv3d(32, 32, 3, 1, 1),
            nn.ReLU(inplace=True),
            nn.Conv3d(32, 64, 1, 1, 0),
        )

        self.conv3_5 = nn.Sequential(
            nn.Conv3d(64, 32, 1, 1, 0),
            nn.ReLU(inplace=True),
            nn.Conv3d(32, 32, 3, 1, 2, 2),
            nn.Conv3d(32, 32, 3, 1, 2, 2),
            nn.ReLU(inplace=True),
            nn.Conv3d(32, 64, 1, 1, 0),
        )

        self.conv3_7 = nn.Sequential(
            nn.Conv3d(64, 32, 1, 1, 0),
            nn.ReLU(inplace=True),
            nn.Conv3d(32, 32, 3, 1, 2, 2),
            nn.Conv3d(32, 32, 3, 1, 2, 2),
            nn.ReLU(inplace=True),
            nn.Conv3d(32, 64, 1, 1, 0),
        )

        self.conv4_1 = nn.Conv3d(256, 128, 1, 1, 0)
        self.relu4_1 = nn.ReLU(inplace=True)

        self.conv4_2 = nn.Conv3d(128, 128, 1, 1, 0)
        self.relu4_2 = nn.ReLU(inplace=True)

        self.fc12 = nn.Conv3d(128, 12, 1, 1, 0)  # C_NUM = 12, number of classes is 12

        self.softmax = nn.Softmax(dim=1)  # pytorch 0.3.0
        # self.logsoftmax = nn.LogSoftmax(dim=1)

        # ----  weights init
        for m in self.modules():
            if isinstance(m, nn.Conv3d):
                n = m.kernel_size[0] * m.kernel_size[1] * m.kernel_size[2] * m.out_channels
                # nn.init.xavier_normal(m.weight.data, gain=math.sqrt(2. / n))
                # nn.init.xavier_uniform(m.weight.data, gain=math.sqrt(2. / n))
                nn.init.xavier_uniform_(m.weight.data)  # gain=1
                # nn.init.constant(m.bias.data, 0)
        nn.init.normal_(self.conv4_1.weight.data, mean=0, std=0.1)
        nn.init.normal_(self.conv4_2.weight.data, mean=0, std=0.01)
        nn.init.normal_(self.fc12.weight.data, mean=0, std=0.01)

    def forward(self, x_depth, x_tsdf, p):
        # input: x (BS, 3L, 240L, 144L, 240L)
        # print('SSC: x.shape', x.shape)
        # x0 = self.conv2d(x)
        x0_depth = self.conv2d_depth(x_depth)
        x0_depth = F.relu(self.res_depth(x0_depth) + x0_depth, inplace=True)
        x0_depth = self.project_layer(x0_depth, p)

        x1_depth = self.pool1(x0_depth)
        x1_depth = F.relu(x1_depth, inplace=True)

        x2_1_depth = self.reduction2_1(x1_depth)  # (BS, 32L, 120L, 72L, 120L)
        x2_2_depth = self.conv2_1(x1_depth)
        x2_depth = x2_1_depth + x2_2_depth
        x2_depth = F.relu(x2_depth, inplace=True)

        x1_tsdf = self.pool2(x_tsdf)            # (BS, 16L, 120L, 72L, 120L)
        x1_tsdf = F.relu(x1_tsdf, inplace=True)
        # print 'SSC: x1', x1.size()

        x2_1_tsdf = self.reduction2_2(x1_tsdf)     # (BS, 32L, 120L, 72L, 120L)
        x2_2_tsdf = self.conv2_2(x1_tsdf)
        x2_tsdf = x2_1_tsdf + x2_2_tsdf
        x2_tsdf = F.relu(x2_tsdf, inplace=True)

        # print('SSC: x2_depth.shape', x2_depth.shape)
        # print('SSC: x2_tsdf.shape', x2_tsdf.shape)

        # x2 = torch.cat((x2_depth, x2_tsdf), dim=1)
        # print('SSC: x0.shape', x0.shape)  # (BS, c, 480L, 640L)

        # -------------------------------------------------------------------
        # 2D 转3D
        # bs, c, imgH, imgW = x0.shape
        # src = x0.view(bs, c, -1)
        # p = p.view(bs, 1, -1)
        # index = p.expand(-1, c, -1)  # expand to c channels
        #
        # out = x0.new_zeros((bs, c, 240*144*240))
        # out, _ = scatter_max(src, index, out=out)  # dim_size=240*144*240,
        # x_3d = out.view(bs, c, 240, 144, 240)  # (BS, c, vW, vH, vD)
        # x_3d = x_3d.permute(0, 1, 4, 3, 2)     # (BS, c, vW, vH, vD)--> (BS, c, vD, vH, vW)

        # x_3d = self.project_layer(x0, p)

        # ---------------------------------------------------
        # print 'SSC: x_3d', x_3d.size()
        # x1 = self.pool1(x0)            # (BS, 16L, 120L, 72L, 120L)

        # x_2 = self.pool2(x2)            # x_2: (BS, 32L, 60L, 36L, 60L)
        # x_2 = F.relu(x_2, inplace=True)
        # print 'SSC: x', x.size()

        x3_1_depth = self.reduction3_1(x2_depth)  # (BS, 64L, 60L, 36L, 60L)
        x3_2_depth = self.conv3_1(x2_depth)
        x_3_depth = x3_1_depth + x3_2_depth
        x_3_depth = F.relu(x_3_depth, inplace=True)
        # print('SSC: x_3_depth', x_3_depth.size())

        x3_1_tsdf = self.reduction3_2(x2_tsdf)   # (BS, 64L, 60L, 36L, 60L)
        x3_2_tsdf = self.conv3_2(x2_tsdf)        #
        x_3_tsdf = x3_1_tsdf + x3_2_tsdf
        x_3_tsdf = F.relu(x_3_tsdf, inplace=True)
        # print('SSC: x_3_tsdf', x_3_tsdf.size())

        x_3 = torch.cat((x_3_depth, x_3_tsdf), dim=1)

        # ---- 1/4
        x_4 = self.conv3_3(x_3) + x_3
        x_4 = F.relu(x_4, inplace=True)
        # print 'SSC: x_4', x_4.size()

        x_5 = self.conv3_5(x_4) + x_4
        x_5 = F.relu(x_5, inplace=True)
        # print 'SSC: x_5', x_5.size()

        x_6 = self.conv3_7(x_5) + x_5
        x_6 = F.relu(x_6, inplace=True)
        # print 'SSC: x_6', x_6.size()

        x_6 = torch.cat((x_3, x_4, x_5, x_6), dim=1)  # channels concatenate
        # x_6 = F.relu(x_6)
        # print('SSC: channels concatenate x', x.size())  # (BS, 256L, 60L, 36L, 60L)

        x_6 = self.conv4_1(x_6)       # (BS, 128L, 60L, 36L, 60L)
        x_6 = F.relu(x_6, inplace=True)
        # x_6 = self.relu4_1(x_6)

        x_6 = self.conv4_2(x_6)       # (BS, 128L, 60L, 36L, 60L)
        x_6 = F.relu(x_6, inplace=True)
        # print 'SSC: x_6', x_6.size()

        y = self.fc12(x_6)        # (BS, 12L, 60L, 36L, 60L)
        # print 'SSC: y', y.size()
        # y = y.permute(0, 2, 3, 4, 1).contiguous()  # (bs, _c, _d, _h, _w) --> # (bs, _d, _h, _w, _c)
        return y  # x_6, 1/4 res feature map; x2, 1/2 res feature map; y, 1/4 res output.
        # return y