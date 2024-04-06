import os
import random
from random import Random

import Augmentor
import numpy as np
import torch
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import datasets as dset, transforms

def get_train_validation_loader(data_dir, batch_size, num_train, augment, way, trials, shuffle, seed, num_workers,
                                pin_memory):
    train_dir = os.path.join(data_dir, 'train')
    val_dir = os.path.join(data_dir, 'valid')

    train_transform = transforms.Compose([
        transforms.Resize((105, 105)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.8444], std=[0.5329])
    ])

    val_transform = transforms.Compose([
        transforms.Resize((105, 105)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.8444], std=[0.5329])
    ])

    train_dataset = dset.ImageFolder(train_dir, transform=train_transform)
    train_dataset = OmniglotTrain(train_dataset, num_train, augment)
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=shuffle, num_workers=num_workers,
                              pin_memory=pin_memory)

    val_dataset = dset.ImageFolder(val_dir, transform=val_transform)
    val_dataset = OmniglotTest(val_dataset, trials, way, seed)
    val_loader = DataLoader(val_dataset, batch_size=way, shuffle=False, num_workers=num_workers,
                            pin_memory=pin_memory)

    return train_loader, val_loader

def get_test_loader(data_dir, way, trials, seed, num_workers, pin_memory):
    test_dir = os.path.join(data_dir, 'test')

    test_transform = transforms.Compose([
        transforms.Resize((105, 105)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.8444], std=[0.5329])
    ])

    test_dataset = dset.ImageFolder(test_dir, transform=test_transform)
    test_dataset = OmniglotTest(test_dataset, trials=trials, way=way, seed=seed)
    test_loader = DataLoader(test_dataset, batch_size=way, shuffle=False, num_workers=num_workers,
                             pin_memory=pin_memory)

    return test_loader


# adapted from https://github.com/fangpin/siamese-network
class OmniglotTrain(Dataset):

    def __init__(self, dataset, num_train, augment=False):
        self.dataset = dataset
        self.num_train = num_train
        self.augment = augment

    def __len__(self):
        return self.num_train

    def __getitem__(self, index):
        if index % 2 == 1:
            label = 1.0
            idx = random.randint(0, len(self.dataset.classes) - 1)
            image_list = [x for x in self.dataset.imgs if x[1] == idx]
            image1 = random.choice(image_list)
            image2 = random.choice(image_list)
            while image1[0] == image2[0]:
                image2 = random.choice(image_list)
        else:
            label = 0.0
            image1 = random.choice(self.dataset.imgs)
            image2 = random.choice(self.dataset.imgs)
            while image1 == image2:
                image2 = random.choice(self.dataset.imgs)

        trans = transforms.Compose([
            transforms.Resize((105, 105)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.8444], std=[0.5329])
        ])

        image1 = Image.open(image1[0]).convert('L')
        image2 = Image.open(image2[0]).convert('L')
        image1 = trans(image1)
        image2 = trans(image2)
        label = torch.tensor(label, dtype=torch.float32)

        return image1, image2, label

# class OmniglotTest(Dataset):
#     def __init__(self, dataset, trials, way, seed=0):
#         self.dataset = dataset
#         self.trials = trials
#         self.way = way
#         self.seed = seed
#         self.image1 = None
#
#     def __len__(self):
#         return self.trials * self.way
#
#     def __getitem__(self, index):
#         rand = Random(self.seed + index)
#         if index % self.way == 0:
#             label = 1.0
#             idx = rand.randint(0, len(self.dataset.classes) - 1)
#             image_list = [x for x in self.dataset.imgs if x[1] == idx]
#             self.image1 = rand.choice(image_list)
#             image2 = rand.choice(image_list)
#             while self.image1[0] == image2[0]:
#                 image2 = rand.choice(image_list)
#         else:
#             label = 0.0
#             image2 = random.choice(self.dataset.imgs)
#             while self.image1[1] == image2[1]:
#                 image2 = random.choice(self.dataset.imgs)
#
#         trans = transforms.Compose([
#             transforms.Resize((105, 105)),
#             transforms.ToTensor(),
#             transforms.Normalize(mean=[0.8444], std=[0.5329])
#         ])
#
#         image1 = Image.open(self.image1[0]).convert('L')
#         image2 = Image.open(image2[0]).convert('L')
#         image1 = trans(image1)
#         image2 = trans(image2)
#
#         return image1, image2, torch.tensor(label, dtype=torch.float32)

# class OmniglotTest(Dataset):
#     def __init__(self, dataset, trials, way, seed=0):
#         self.dataset = dataset
#         self.trials = trials
#         self.way = way
#         self.seed = seed
#         self.image1 = None
#
#     def __len__(self):
#         return self.trials * self.way

    # def __getitem__(self, index):
    #     rand = Random(self.seed + index)
    #     if index % self.way == 0:  # 새로운 'way'마다 anchor 이미지를 선택
    #         idx = rand.randint(0, len(self.dataset.classes) - 1)
    #         image_list = [x for x in self.dataset.imgs if x[1] == idx]
    #         self.image1 = rand.choice(image_list)  # anchor 이미지 선택
    #         image2 = rand.choice(image_list)
    #         while self.image1[0] == image2[0]:  # 다른 이미지 선택
    #             image2 = rand.choice(image_list)
    #         label = 1.0  # 같은 클래스
    #     else:
    #         image2 = random.choice(self.dataset.imgs)
    #         while self.image1[1] == image2[1]:  # 다른 클래스 이미지 선택
    #             image2 = random.choice(self.dataset.imgs)
    #         label = 0.0  # 다른 클래스
    #
    #     trans = transforms.Compose([
    #         transforms.Resize((105, 105)),
    #         transforms.ToTensor(),
    #         transforms.Normalize(mean=[0.8444], std=[0.5329])
    #     ])
    #
    #     image1 = Image.open(self.image1[0]).convert('L')
    #     image2 = Image.open(image2[0]).convert('L')
    #     image1 = trans(image1)
    #     image2 = trans(image2)
    #
    #     anchor_label = self.image1[1]  # anchor 이미지의 클래스 인덱스
    #
    #     return image1, image2, torch.tensor(label, dtype=torch.float32), torch.tensor(anchor_label, dtype=torch.int64)

class OmniglotTest(Dataset):
    def __init__(self, dataset, trials, way, seed=0):
        self.dataset = dataset
        self.trials = trials
        self.way = way
        self.seed = seed
        self.image1 = None

    def __len__(self):
        return self.trials * self.way

    def __getitem__(self, index):
        rand = Random(self.seed + index)
        if index % self.way == 0:  # 새로운 'way'마다 anchor 이미지를 선택
            idx = rand.randint(0, len(self.dataset.classes) - 1)
            image_list = [x for x in self.dataset.imgs if x[1] == idx]
            self.image1 = rand.choice(image_list)  # anchor 이미지 선택
            image2 = rand.choice(image_list)
            while self.image1[0] == image2[0]:  # 다른 이미지 선택
                image2 = rand.choice(image_list)
            label = 1.0  # 같은 클래스
        else:
            image2 = random.choice(self.dataset.imgs)
            while self.image1[1] == image2[1]:  # 다른 클래스 이미지 선택
                image2 = random.choice(self.dataset.imgs)
            label = 0.0  # 다른 클래스

        # 이미지 변환을 적용하기 전에 레이블 정보를 추출
        image2_label = image2[1]  # 이미지 변환 전에 image2의 레이블을 추출

        # 이미지 변환 적용
        trans = transforms.Compose([
            transforms.Resize((105, 105)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.8444], std=[0.5329])
        ])

        image1 = Image.open(self.image1[0]).convert('L')
        image2 = Image.open(image2[0]).convert('L')
        image1 = trans(image1)
        image2 = trans(image2)

        anchor_label = self.image1[1]  # anchor 이미지의 클래스 인덱스

        return image1, image2, torch.tensor(label, dtype=torch.float32), torch.tensor(anchor_label,dtype=torch.int64), torch.tensor(image2_label, dtype=torch.int64)

