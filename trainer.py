import os
from glob import glob

import torch
import torch.optim as optim
from torch.utils.tensorboard import SummaryWriter
from tqdm import tqdm

import config_maker
import visual
from data_loader import get_train_validation_loader, get_test_loader
from model import SiameseNet
from utils import AverageMeter
from scheduler import OneCyclePolicy




class Trainer(object):
    """
    Trainer encapsulates all the logic necessary for training
    the Siamese Network model.

    All hyperparameters are provided by the user in the
    config file.
    """

    def __init__(self, config):
        """
        Construct a new Trainer instance.

        Args
        ----
        - config: object containing command line arguments.
        """
        self.config = config
        self.device = torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")

    def train(self):
        # Dataloader
        train_loader, valid_loader = get_train_validation_loader(self.config.data_dir, self.config.batch_size,
                                                                 self.config.num_train,
                                                                 self.config.augment, self.config.way,
                                                                 self.config.valid_trials,
                                                                 self.config.shuffle, self.config.seed,
                                                                 self.config.num_workers, self.config.pin_memory)

        # Model, Optimizer, criterion
        model = SiameseNet()
        if self.config.optimizer == "SGD":
            optimizer = optim.SGD(model.parameters(), lr=self.config.lr)
        else:
            optimizer = optim.Adam(model.parameters())
        criterion = torch.nn.BCEWithLogitsLoss()

        if self.config.use_gpu:
            model.cuda()

        # Load check point
        if self.config.resume:
            start_epoch, best_epoch, best_valid_acc, model_state, optim_state = self.load_checkpoint(best=False)
            model.load_state_dict(model_state)
            optimizer.load_state_dict(optim_state)
            one_cycle = OneCyclePolicy(optimizer, self.config.lr,
                                       (self.config.epochs - start_epoch) * len(train_loader),
                                       momentum_rng=[0.85, 0.95])
        else:
            best_epoch = 0
            start_epoch = 0
            best_valid_acc = 0
            one_cycle = OneCyclePolicy(optimizer, self.config.lr, self.config.epochs * len(train_loader),
                                       momentum_rng=[0.85, 0.95])

        # create tensorboard summary and add model structure.
        writer = SummaryWriter(os.path.join(self.config.logs_dir, 'logs'), filename_suffix=self.config.num_model)
        im1, im2, label, _, _ = next(iter(valid_loader))
        writer.add_graph(model, [im1.to(self.device), im2.to(self.device)])

        counter = 0
        num_train = len(train_loader)
        num_valid = len(valid_loader)
        print(
            f"[*] Train on {len(train_loader.dataset)} sample pairs, validate on {valid_loader.dataset.trials} trials")

        # Train & Validation
        main_pbar = tqdm(range(start_epoch, self.config.epochs), initial=start_epoch, position=0,
                         total=self.config.epochs, desc="Process")
        for epoch in main_pbar:
            train_losses = AverageMeter()
            valid_losses = AverageMeter()

            # TRAIN
            model.train()
            train_pbar = tqdm(enumerate(train_loader), total=num_train, desc="Train", position=1, leave=False)
            for i, (x1, x2, y) in train_pbar:
                if self.config.use_gpu:
                    x1, x2, y = x1.to(self.device), x2.to(self.device), y.to(self.device)
                out = model(x1, x2)
                loss = criterion(out, y.unsqueeze(1))

                # compute gradients and update
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                one_cycle.step()

                # store batch statistics
                train_losses.update(loss.item(), x1.shape[0])

                # log loss
                writer.add_scalar("Loss/Train", train_losses.val, epoch * len(train_loader) + i)
                train_pbar.set_postfix_str(f"loss: {train_losses.val:0.3f}")

            # VALIDATION
            model.eval()
            valid_acc = 0
            correct_sum = 0
            valid_pbar = tqdm(enumerate(valid_loader), total=num_valid, desc="Valid", position=1, leave=False)
            with torch.no_grad():
                for i, (x1, x2, label, _, _) in valid_pbar:  # 언패킹 방식이 수정됨

                    if self.config.use_gpu:
                        x1, x2, label = x1.to(self.device), x2.to(self.device), label.to(self.device)  # label도 GPU로 이동

                    # 모델을 통해 logit을 계산
                    out = model(x1, x2)

                    # 손실 계산
                    loss = criterion(out, label.unsqueeze(1))  # y 대신 label 사용

                    y_pred = torch.sigmoid(out)
                    y_pred = torch.argmax(y_pred)
                    if y_pred == 0:
                        correct_sum += 1

                    # store batch statistics
                    valid_losses.update(loss.item(), x1.shape[0])

                    # compute acc and log
                    valid_acc = correct_sum / num_valid
                    writer.add_scalar("Loss/Valid", valid_losses.val, epoch * len(valid_loader) + i)
                    valid_pbar.set_postfix_str(f"accuracy: {valid_acc:0.3f}")
            writer.add_scalar("Acc/Valid", valid_acc, epoch)

            # check for improvement
            if valid_acc > best_valid_acc:
                is_best = True
                best_valid_acc = valid_acc
                best_epoch = epoch
                counter = 0
            else:
                is_best = False
                counter += 1

            # checkpoint the model
            if counter > self.config.train_patience:
                print("[!] No improvement in a while, stopping training.")
                return

            if is_best or epoch % 5 == 0 or epoch == self.config.epochs:
                self.save_checkpoint(
                    {
                        'epoch': epoch,
                        'model_state': model.state_dict(),
                        'optim_state': optimizer.state_dict(),
                        'best_valid_acc': best_valid_acc,
                        'best_epoch': best_epoch,
                    }, is_best
                )

            main_pbar.set_postfix_str(f"best acc: {best_valid_acc:.3f} best epoch: {best_epoch} ")

            tqdm.write(
                f"[{epoch}] train loss: {train_losses.avg:.3f} - valid loss: {valid_losses.avg:.3f} - valid acc: {valid_acc:.3f} {'[BEST]' if is_best else ''}")

        # release resources
        writer.close()

    # def test(self):
    #     config = config_maker.get_config()
    #     # Load best model
    #     model = SiameseNet()
    #     _, _, _, model_state, _ = self.load_checkpoint(best=self.config.best)
    #     model.load_state_dict(model_state)
    #     if self.config.use_gpu:
    #         model.cuda()
    #
    #     test_loader = get_test_loader(self.config.data_dir, self.config.way, self.config.test_trials,
    #                                   self.config.seed, self.config.num_workers, self.config.pin_memory)
    #
    #     correct_sum = 0
    #     num_test = test_loader.dataset.trials
    #     print(f"[*] Test on {num_test} pairs.")
    #
    #     pbar = tqdm(enumerate(test_loader), total=num_test, desc="Test")
    #     with torch.no_grad():
    #         for i, (x1, x2, _) in pbar:
    #
    #             if self.config.use_gpu:
    #                 x1, x2 = x1.to(self.device), x2.to(self.device)
    #
    #             # Compute log probabilities
    #             out = model(x1, x2)
    #
    #             y_pred = torch.sigmoid(out)
    #             y_pred = torch.argmax(y_pred).item()
    #             if y_pred == 0:
    #                 correct_sum += 1
    #
    #             # Call visualize_prediction with the current index i
    #             visual.visualize_prediction(x1[0], x2[0], y_pred, i, config.logs_dir)
    #
    #             pbar.set_postfix_str(f"accuracy: {correct_sum / num_test}")
    #
    #     test_acc = (100. * correct_sum) / num_test
    #     print(f"Test Acc: {correct_sum}/{num_test} ({test_acc:.2f}%)")

    # def test(self):
    #     config = config_maker.get_config()
    #     # Load best model
    #     model = SiameseNet()
    #     _, _, _, model_state, _ = self.load_checkpoint(best=self.config.best)
    #     model.load_state_dict(model_state)
    #     if self.config.use_gpu:
    #         model.cuda()
    #
    #     test_loader = get_test_loader(self.config.data_dir, self.config.way, self.config.test_trials,
    #                                   self.config.seed, self.config.num_workers, self.config.pin_memory)
    #
    #     correct_sum = 0
    #     num_test = test_loader.dataset.trials
    #     print(f"[*] Test on {num_test} pairs.")
    #
    #     pbar = tqdm(enumerate(test_loader), total=num_test, desc="Test")
    #     with torch.no_grad():
    #         for i, (x1, x2, similarity_labels, anchor_labels) in pbar:
    #
    #             if self.config.use_gpu:
    #                 x1, x2 = x1.to(self.device), x2.to(self.device)
    #
    #             # Compute log probabilities
    #             out = model(x1, x2)
    #
    #             y_pred = torch.sigmoid(out)
    #             y_pred = torch.argmax(y_pred).item()
    #             if y_pred == 0:
    #                 correct_sum += 1
    #
    #             # 이미 .item()을 사용하여 float으로 변환된 값을 받았으므로, 추가적인 .item() 호출은 필요 없음
    #             similarity_label = similarity_labels[0].item()  # 첫 번째 요소의 레이블만 사용
    #             anchor_label = anchor_labels[0].item()  # 첫 번째 요소의 레이블만 사용
    #
    #             # Call visualize_prediction with the current index i and anchor_label
    #             visual.visualize_prediction(x1[0], x2[0], y_pred, anchor_label, i, config.logs_dir)
    #
    #             pbar.set_postfix_str(f"accuracy: {correct_sum / num_test}")
    #
    #     test_acc = (100. * correct_sum) / num_test
    #     print(f"Test Acc: {correct_sum}/{num_test} ({test_acc:.2f}%)")

    def test(self):
        config = config_maker.get_config()
        # Load best model
        model = SiameseNet()
        _, _, _, model_state, _ = self.load_checkpoint(best=self.config.best)
        model.load_state_dict(model_state)
        if self.config.use_gpu:
            model.cuda()

        test_loader = get_test_loader(self.config.data_dir, self.config.way, self.config.test_trials,
                                      self.config.seed, self.config.num_workers, self.config.pin_memory)

        correct_sum = 0
        num_test = test_loader.dataset.trials
        print(f"[*] Test on {num_test} pairs.")

        pbar = tqdm(enumerate(test_loader), total=num_test, desc="Test")
        with torch.no_grad():
            for i, (x1, x2, similarity_labels, anchor_labels, x2_labels) in pbar:

                if self.config.use_gpu:
                    x1, x2 = x1.to(self.device), x2.to(self.device)

                # Compute log probabilities
                out = model(x1, x2)

                y_pred = torch.sigmoid(out)
                y_pred = torch.argmax(y_pred).item()
                if y_pred == 0:
                    correct_sum += 1

                # 이미 .item()을 사용하여 float으로 변환된 값을 받았으므로, 추가적인 .item() 호출은 필요 없음
                similarity_label = similarity_labels[0].item()  # 첫 번째 요소의 레이블만 사용
                anchor_label = anchor_labels[0].item()  # 첫 번째 요소의 레이블만 사용
                x2_label = x2_labels[0].item()

                # Call visualize_prediction with the current index i and anchor_label
                visual.visualize_prediction(x1[0], x2[0], y_pred, anchor_label, x2_label, i, config.logs_dir)

                pbar.set_postfix_str(f"accuracy: {correct_sum / num_test}")

        test_acc = (100. * correct_sum) / num_test
        print(f"Test Acc: {correct_sum}/{num_test} ({test_acc:.2f}%)")


    def save_checkpoint(self, state, is_best):

        if is_best:
            filename = './models/best_model.pt'
        else:
            filename = f'./models/model_ckpt_{state["epoch"]}.pt'

        model_path = os.path.join(self.config.logs_dir, filename)
        torch.save(state, model_path)

    def load_checkpoint(self, best):
        print(f"[*] Loading model Num.{self.config.num_model}...", end="")

        if best:
            model_path = os.path.join(self.config.logs_dir, './models/best_model.pt')
        else:
            model_path = sorted(glob(self.config.logs_dir + './models/model_ckpt_*.pt'), key=len)[-1]

        ckpt = torch.load(model_path)

        if best:
            print(
                f"Loaded {os.path.basename(model_path)} checkpoint @ epoch {ckpt['epoch']} with best valid acc of {ckpt['best_valid_acc']:.3f}")
        else:
            print(f"Loaded {os.path.basename(model_path)} checkpoint @ epoch {ckpt['epoch']}")

        return ckpt['epoch'], ckpt['best_epoch'], ckpt['best_valid_acc'], ckpt['model_state'], ckpt['optim_state']