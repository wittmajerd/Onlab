import torch
from torch.utils.data import Dataset
from torchvision.transforms import Normalize
import numpy as np
import os

def calculate_mean_and_std(path, train_files, biosensor_length=16):
    # Preallocate a tensor of the correct size
    data = torch.empty((len(train_files), biosensor_length, 80, 80))

    for i, file in enumerate(train_files):
        loaded_data = np.load(path + file)

        biosensor = torch.from_numpy(loaded_data['biosensor'].astype(np.float32))
        indices = np.linspace(0, biosensor.shape[0] - 1, biosensor_length, dtype=int)
        bio = biosensor[indices]

        data[i] = bio  # Fill the preallocated tensor

    return data.mean(), data.std()


class BiosensorDataset(Dataset):
    def __init__(self, path, files, mean, std, mask_type, biosensor_length=128, mask_size=80):
        self.path = path
        self.files = files
        self.transform = Normalize(mean=mean, std=std)
        self.mask_type = mask_type
        self.length = biosensor_length
        self.mask_size = mask_size

    def __getitem__(self, index):
        data = np.load(self.path + self.files[index])
        bio = self.uniform_time_dim(torch.from_numpy(data['biosensor'].astype(np.float32)))
        mask = self.uniform_mask(torch.from_numpy(data['mask'].astype(self.mask_type)), data['cell_centers'])
        bio = self.transform(bio)
        return bio, mask
        
    def __len__(self):
        return len(self.files)
    
    def uniform_time_dim(self, biosensor):
        indices = np.linspace(0, biosensor.shape[0] - 1, self.length, dtype=int)
        return biosensor[indices]
    
    def uniform_mask(self, mask, centers):
        interpolated_mask = torch.nn.functional.interpolate(mask.unsqueeze(0).unsqueeze(0).float(), size=(self.mask_size, self.mask_size), mode='nearest').squeeze(0).squeeze(0).byte()
        
        x_scale = mask.shape[0] / self.mask_size
        y_scale = mask.shape[1] / self.mask_size
        
        scaled_centers = centers / [x_scale, y_scale]

        # Add the cell centers to the mask
        indices = np.transpose(scaled_centers.astype(int))
        if self.mask_type == bool:
            interpolated_mask[indices[0], indices[1]] = True
        else:
            interpolated_mask[indices[0], indices[1]] = 255
        
        return interpolated_mask