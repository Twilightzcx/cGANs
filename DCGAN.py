import torch
import time
from torch import nn
import torchvision.datasets
from torchvision import transforms
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from utils import save_run, generate_noise, read_saved_run, get_random_params, purge_poor_runs
from inception_score import get_inception_score
plt.rcParams['image.cmap'] = 'gray'

def generate_nosie(batch_size, dim=100):
    noise = torch.randn(batch_size, dim, 1, 1)
    return noise

class Discriminator(nn.Module):
    def __init__(self):
        super(Discriminator, self).__init__()
        self.conv1 = nn.Sequential(
            nn.Conv2d(1, 32, [5,5], stride=[1,1]),
            nn.LeakyReLU(negative_slope=.01),
            nn.MaxPool2d([2,2], stride=[2,2]))
        self.conv2 = nn.Sequential(
            nn.Conv2d(32, 64, [5,5], stride=[1,1]),
            nn.LeakyReLU(negative_slope=.01),
            nn.MaxPool2d([2,2], stride=[2,2]))
        self.fc1 = nn.Sequential(
            nn.Linear((64*5*5), (64*5*5)),
            nn.LeakyReLU(negative_slope=.01))
        self.fc2 = nn.Sequential(
            nn.Linear((64*5*5), 1),
            nn.Sigmoid())


    def forward(self, x):
        out = self.conv1(x)
        out = self.conv2(out)
        out = out.view(out.shape[0], -1)
        out = self.fc1(out)
        out = self.fc2(out)
        return out

class Generator(nn.Module):
    def __init__(self):
        super(Generator, self).__init__()
        self.deconv1 = nn.Sequential(
            nn.ConvTranspose2d(100, 128, [2,2], stride=[1,1]),
            nn.BatchNorm2d(128),
            nn.ReLU())
        self.deconv2 = nn.Sequential(
            nn.ConvTranspose2d(128, 256, [3,3], stride=[1,1]),
            nn.BatchNorm2d(256),
            nn.ReLU())
        self.deconv3 = nn.Sequential(
            nn.ConvTranspose2d(256, 256, [4,4], stride=[2,2], padding=1),
            nn.BatchNorm2d(256),
            nn.ReLU())
        self.deconv4 = nn.Sequential(
            nn.ConvTranspose2d(256, 128, [4,4], stride=[2,2], padding=1),
            nn.BatchNorm2d(128))
        self.deconv5 = nn.Sequential(
            nn.ConvTranspose2d(128, 1, [4,4], stride=[2,2], padding=1),
            nn.Tanh())

    def forward(self, x):
        # print("x", x.shape)
        out = self.deconv1(x)
        out = self.deconv2(out)
        out = self.deconv3(out)
        out = self.deconv4(out)
        out = self.deconv5(out)
        return out


    def weight_init(m, mean, std):
        if isinstance(m, nn.ConvTranspose2d) or isinstance(m, nn.Conv2d):
            m.weight.data.normal_(mean, std)
            m.bias.data.zero_()

def create_optimizer(model, lr=.01, betas=None):
    if betas == None:
        optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    else:
        optimizer = torch.optim.Adam(model.parameters(), lr=lr, betas=betas)
    return optimizer

def save_images(generator, epoch, i, filename_prefix):
    fig = plt.figure(figsize=(10, 10))
    gs = gridspec.GridSpec(10, 10)
    gs.update(wspace=.05, hspace=.05)
    z = generate_nosie(100)
    images_fake = generator(z)
    images_fake = images_fake.data.data.cpu().numpy()
    for img_num, sample in enumerate(images_fake):
        ax = plt.subplot(gs[img_num])
        plt.axis('off')
        ax.set_xticklabels([])
        ax.set_yticklabels([])
        ax.set_aspect('equal')
        plt.imshow(sample.reshape(32, 32), cmap='Greys_r')

    filename = filename_prefix + str(epoch) + "-" + str(i) 
    plt.savefig("./generated_images/" + filename, bbox_inches="tight" )
    plt.close(fig)


def train_gan(discriminator, generator, image_loader, num_epochs, batch_size, g_lr, d_lr, dtype, filename_prefix="DCGAN-", save_images=True):
    iters = 0
    d_optimizer = create_optimizer(discriminator, lr=d_lr, betas=(.5, .999))
    g_optimizer = create_optimizer(generator, lr=g_lr, betas=(.5, .999))
    BCELoss = nn.BCELoss()
    for epoch in range(num_epochs):
        for x, _ in image_loader:
            if x.shape[0] != batch_size:
                continue
            real_data = x.type(dtype)

            z = generate_nosie(batch_size)
            fake_images = generator(z)
            g_result = discriminator(fake_images).squeeze()
            g_cost = BCELoss(g_result, torch.ones(batch_size))
            g_cost.backward()
            g_optimizer.step()
            g_optimizer.zero_grad()

            d_optimizer.zero_grad()
            z = generate_nosie(batch_size)
            fake_images = generator(z)
            d_spred_fake = discriminator(fake_images).squeeze()
            d_cost_fake = BCELoss(d_spred_fake, torch.zeros(batch_size))
            d_spred_real = discriminator(real_data).squeeze()
            d_cost_real = BCELoss(d_spred_real, torch.ones(batch_size))
            d_cost = d_cost_real + d_cost_fake
            d_cost.backward()
            d_optimizer.step()
            iters += 1
        if save_images:
            save_images(generator, epoch, iters, filename_prefix)
        print("Epoch", epoch, "Iter", iters)
        print("d_cost", d_cost)
        print("g_cost", g_cost)

    return discriminator, generator

if __name__ == "__main__":
    filename = "dcgan"
    d_filename = "D_mnist"
    g_filename = "G_mnist"
    batch_size = 128
    img_size = 32
    num_epochs = 10
    if torch.cuda.is_available():
        print("Running On GPU :)")
        torch.set_default_tensor_type("torch.cuda.FloatTensor")
        torch.backends.cudnn.benchmark = True
        dtype = torch.cuda.FloatTensor
        use_cuda = True
    else:
        print("Running On CPU :(")
        print("This may take a while")
        use_cuda = False
        dtype = torch.FloatTensor

    transform = transforms.Compose([
        transforms.Resize(img_size),
        transforms.ToTensor(),
        transforms.Normalize(mean=(0.5, 0.5, 0.5), std=(0.5, 0.5, 0.5))])

    mnist_train = torchvision.datasets.EMNIST('./EMNIST_data', train=True, download=True, transform=transform, split="letters")
    train_loader = torch.utils.data.DataLoader(mnist_train, batch_size=batch_size, shuffle=True)
    mnist_test = torchvision.datasets.EMNIST('./EMNIST_data', train=False, download=True, transform=transform, split="letters")
    test_loader = torch.utils.data.DataLoader(mnist_test, batch_size=batch_size,  shuffle=True)


    # discriminator, generator = train_gan(discriminator, generator, train_loader, 10, 128, .0002, .0002, dtype)
    # torch.save(generator.state_dict(), generator_filename + ".pt")
    # torch.save(discriminator.state_dict(), discriminator_filename + ".pt")
    torch.backends.cudnn.benchmark = True
    discriminator = Discriminator()
    generator = Generator()
    if use_cuda:
        torch.backends.cudnn.benchmark = True
        discriminator.cuda()
        generator.cuda()
        torch.backends.cudnn.benchmark = True

    random_lrs = get_random_params(.00002, .002, 10)
    run_stats = []
    filenames = []
    for lr in random_lrs:
        print('lr', lr)
        cur_filename_info = str(lr) + "-" + str(num_epochs) + "-" + str(int(time.time()))
        cur_filename = filename + "-" + cur_filename_info
        filenames += [cur_filename]
        cur_g_filename = g_filename + "-" + cur_filename_info
        cur_d_filename = d_filename + "-" + cur_filename_info
        discriminator, generator = train_gan(discriminator, generator, train_loader, num_epochs, batch_size, lr, lr, dtype, save_images=False)
        fake_images = []
        for i in range(16):
            fake_images += [generator(generate_noise(4))]
        inception_score = get_inception_score(fake_images)
        print("inception score", inception_score)
        stats = save_run(inception_score, lr, num_epochs, discriminator, generator, cur_filename, cur_g_filename, cur_d_filename)
        run_stats += [stats]
    print(run_stats)
    purge_poor_runs([], "./saved_runs/",purge_all=False)
    print("training finished")
