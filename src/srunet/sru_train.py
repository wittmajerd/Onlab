from __future__ import print_function

from math import log10

import torch
import torch.backends.cudnn as cudnn

# from FilterCNN.model import Net

# from progress_bar import progress_bar
from src.srunet.SRU_model import *
from src.srunet.GraLoss import GradientLoss
from src.dice_score import dice_loss

from pytorch_msssim import ssim
import numpy as np

class SRUnetTrainer(object):
    def __init__(self, config, training_loader, testing_loader):
        super(SRUnetTrainer, self).__init__()
        self.CUDA = torch.cuda.is_available()
        self.device = torch.device('cuda' if self.CUDA else 'cpu')
        self.model = None
        self.lr = config.lr
        self.nEpochs = config.nEpochs
        self.criterion = None
        self.optimizer = None
        self.scheduler = None
        self.seed = config.seed
        self.upscale_factor = config.upscale_factor
        self.training_loader = training_loader
        self.testing_loader = testing_loader
        self.in_channels = config.in_channels
        self.classes = config.classes

    def build_model(self):
        if self.upscale_factor==2:
            self.model = UNet2(self.in_channels, self.classes).to(self.device)
        if self.upscale_factor==4:
            self.model = UNet4(self.in_channels, self.classes).to(self.device)
        if self.upscale_factor==8:
            self.model = UNet8(self.in_channels, self.classes).to(self.device)
        if self.upscale_factor==16:
            self.model = UNet16(self.in_channels, self.classes).to(self.device)
        self.model.weight_init(mean=0.0, std=0.01)

        self.criterion = torch.nn.MSELoss()
        self.criterion_2 = GradientLoss()
        self.criterion_3 = torch.nn.L1Loss()
        self.criterion_4 = torch.nn.BCEWithLogitsLoss()

        torch.manual_seed(self.seed)

        print('# model parameters:', sum(param.numel() for param in self.model.parameters()))
        print(self.device)

        if self.CUDA:
            torch.cuda.manual_seed(self.seed)
            cudnn.benchmark = True
            self.criterion.cuda()
            self.criterion_2.cuda()

        self.optimizer = torch.optim.Adam(self.model.parameters(), lr=self.lr, weight_decay=1e-6)   #,weight_decay=1e-4
        self.scheduler = torch.optim.lr_scheduler.MultiStepLR(self.optimizer, milestones=[50,100,150,200,300,400,500,1000], gamma=0.5)

    def save_model(self):
        model_out_path = "checkpoints/sru_save.pth"
        torch.save(self.model, model_out_path)
        print("Checkpoint saved to {}".format(model_out_path))

    def train(self):
        self.model.train()
        train_loss = 0
        for batch_num, (data, target) in enumerate(self.training_loader):
            data, target = data.to(self.device), target.to(self.device)
            self.optimizer.zero_grad()
            prediction = self.model(data)

            # loss1 = self.criterion_3(prediction, target)    #!!!!!
            # loss2 = self.criterion_2(prediction, target)    #!!!!!!!!
            # loss_ssim = 1 - ssim(prediction.float(), target.unsqueeze(1).float())
            # #loss = loss1+loss2     #!!!!!!!!!
            # loss = loss1+0.1*loss_ssim

            loss = self.criterion_4(prediction.float(), target.unsqueeze(1).float())
            loss += dice_loss(
                        prediction.squeeze(1).float(),
                        target.float(),
                        multiclass=False
                    )
            '''
            print("\nloss1")
            print(loss1.cpu().detach().numpy())
            print("\nloss2")
            print(loss2.cpu().detach().numpy())
            print("\nloss_ssim")
            print(loss_ssim.cpu().detach().numpy())
            '''
            #print(str(loss1.cpu().detach().numpy())+'  '+str(loss_ssim.cpu().detach().numpy()))
            
            train_loss += loss.item()
            loss.backward()
            self.optimizer.step()
            # progress_bar(batch_num, len(self.training_loader), 'Loss: %.4f' % (train_loss / (batch_num + 1)))

        print("    Average Loss: {:.4f}".format(train_loss / len(self.training_loader)))

    def test(self):
        self.model.eval()
        avg_psnr = 0
        avg_ssim = 0
        with torch.no_grad():
            for batch_num, (data, target) in enumerate(self.testing_loader):
                data, target = data.to(self.device), target.to(self.device)
                prediction = self.model(data)
                mse = self.criterion(prediction, target)
                psnr = 10 * log10(1 / mse.item())
                avg_psnr += psnr
                ssim_value = ssim(prediction.float(), target.unsqueeze(1).float())
                #print(ssim_value)
                avg_ssim += ssim_value
                # progress_bar(batch_num, len(self.testing_loader), 'PSNR: %.4f | SSIM: %.4f' % ((avg_psnr / (batch_num + 1)),avg_ssim / (batch_num + 1)))

        print("    Average PSNR: {:.4f} dB".format(avg_psnr / len(self.testing_loader)))

    def run(self):
        self.build_model()
        for epoch in range(1, self.nEpochs + 1):
            print("\n===> Epoch {} starts:".format(epoch))
            self.train()
            self.test()
            self.scheduler.step(epoch)
            if epoch == self.nEpochs:
                self.save_model()
