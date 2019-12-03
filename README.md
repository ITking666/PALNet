# Depth Based Semantic Scene Completion with Position Importance Aware Loss

By Yu Liu*, Jie Li*, Xia Yuan, Chunxia Zhao, Roland Siegwart, Ian Reid and Cesar Cadena (* indicates equal contribution)

## Video Demo: 
https://youtu.be/j-LAMcMh0yg

## Testing
python ./test.py \
--data_test=/path/to/NYUCADtest \
--batch_size=1 \
--workers=4 \
--resume='PALNet_weights.pth.tar'

## Weights
[Model trained on NYUCAD](https://drive.google.com/open?id=1BRNliQmEaPIphZvbzhR55fEHeOh9U9Ix)

## Datasets 
The original dataset is from [SSCNet](https://github.com/shurans/sscnet)

Here is the [NYUCAD](https://drive.google.com/open?id=10Iz7lkJf8kbtUf1OyL-Z1xW6eZRoF3d8) data reproduced from SSCNet for a quick demo.



